#!/usr/bin/env python3
"""Probe the organizers' proxy with the real Qwen models.

    LLM_BASE_URL=... LLM_API_KEY=... python tools/probe_proxy.py [--out runs/probe.json]

Checks, for each of the 4 models:
  1. trivial reply through openJiuwen and through the raw transport;
  2. reported usage (prompt / completion / reasoning tokens) vs our estimate;
  3. tool calling (needed by the agent);
  4. a small arithmetic task as code (the harness' main LLM pattern).
Writes a JSON report (no secrets) so the team can calibrate the planner.
Also records whether completions ran past max_tokens (per-attempt caps rely
on it) and how far our input-token estimate is from the reported one.
Total cost: roughly 2-4k competition tokens (reasoning models dominate);
hard ceiling --budget (default 8000).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SSRF_PROTECT_ENABLED", "false")
_cwd = Path.cwd()
os.chdir(tempfile.mkdtemp())  # openJiuwen writes ./logs

from harness.budget import BudgetLedger, estimate_tokens  # noqa: E402
from harness.llm import ALL_MODELS, LLM, LLMUnavailable  # noqa: E402
from harness import sandbox  # noqa: E402
from harness.llm_solvers import SYS_CODE, extract_code  # noqa: E402

HELLO = [{"role": "user", "content": "Reply with the number 42 only."}]
TOOL = [{"name": "submit", "description": "Submit the final answer.",
         "parameters": {"type": "object", "properties": {"answer": {"type": "string"}},
                        "required": ["answer"]}}]
TOOL_MSG = [{"role": "system", "content": "Always answer by calling the submit tool."},
            {"role": "user", "content": "What is 6*7? Submit it."}]
MATH = ("A warehouse starts with 1752 boxes. Then the stock is split equally into 2 warehouses "
        "and it keeps one share (rounded down). Then the stock is doubled by merging with a "
        "sister warehouse. Then the stock is split equally into 3 warehouses and it keeps one "
        "share (rounded down). Then the stock is doubled by merging with a sister warehouse. "
        "Then the stock is split equally into 3 warehouses and it keeps one share (rounded "
        "down). How many boxes does it have at the end?")
MATH_EXPECTED = "389"


def effective_max_tokens(model: str, requested: int) -> int:
    """What harness.llm really sends (thinking models get a higher floor)."""
    return requested if "noreason" in model else min(2500, max(requested, 1500))


REQ = {"hello": 64, "tool": 200, "math": 350}


async def one(llm: LLM, led: BudgetLedger, model, transport, kind):
    llm._oj_ok = transport == "openjiuwen"
    n0 = len(led.log)
    t0 = time.time()
    rec = {"model": model, "transport_requested": transport, "test": kind,
           "max_tokens_sent": effective_max_tokens(model, REQ[kind])}
    msgs = HELLO if kind == "hello" else TOOL_MSG if kind == "tool" else [
        {"role": "system", "content": SYS_CODE}, {"role": "user", "content": MATH}]
    rec["in_est"] = int(estimate_tokens(json.dumps(msgs, ensure_ascii=False)
                                        + (json.dumps(TOOL) if kind == "tool" else "")))
    try:
        if kind == "hello":
            r = await llm.chat(HELLO, model=model, max_tokens=64, tag="probe")
            rec["ok"] = "42" in (r["content"] or "")
            rec["content"] = (r["content"] or "")[:200]
        elif kind == "tool":
            r = await llm.chat(TOOL_MSG, model=model, max_tokens=200, tools=TOOL, tag="probe")
            tc = r["tool_calls"]
            rec["tool_calls"] = tc[:2]
            rec["ok"] = bool(tc) and tc[0]["name"] == "submit" and "42" in tc[0]["arguments"]
            rec["content"] = (r["content"] or "")[:200]
        else:
            r = await llm.chat([{"role": "system", "content": SYS_CODE},
                                {"role": "user", "content": MATH}],
                               model=model, max_tokens=350, tag="probe")
            code = extract_code(r["content"] or "")
            out = ""
            if code:
                with tempfile.TemporaryDirectory() as d:
                    rc, out = sandbox.run_python(code, Path(d))
            rec["answer"] = out.strip()[:100]
            rec["ok"] = out.strip().splitlines()[-1:] == [MATH_EXPECTED] if out else False
            rec["content"] = (r["content"] or "")[:400]
        rec["cost"] = round(r["cost"], 1)
    except LLMUnavailable as e:
        rec["ok"] = False
        rec["error"] = str(e)[:300]
    except Exception as e:  # noqa: BLE001
        rec["ok"] = False
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
    rec["backend_used"] = llm.backend_used
    rec["sec"] = round(time.time() - t0, 1)
    if len(led.log) > n0:
        rec["usage"] = led.log[-1]
        rec["calls"] = len(led.log) - n0
        out = int(rec["usage"].get("out", 0) or 0)
        # a proxy that lets completions run past max_tokens breaks per-attempt caps
        rec["over_cap"] = out > rec["max_tokens_sent"]
        ain = int(rec["usage"].get("in", 0) or 0)
        if ain:
            rec["in_est_ratio"] = round(rec["in_est"] / ain, 2)
    return rec


def verdict(results: list[dict], models: list[str]) -> list[str]:
    """Plain-language summary for the team (also stored in the report)."""
    lines = []
    for m in models:
        rs = [r for r in results if r["model"] == m]
        if not rs:
            lines.append(f"{m}: NOT TESTED")
            continue
        ok = sum(1 for r in rs if r.get("ok"))
        errs = sorted({(r.get("error") or "")[:70] for r in rs if r.get("error")})
        via = sorted({r["backend_used"] for r in rs if r.get("ok")})
        reason = max((int(r.get("usage", {}).get("reason", 0) or 0) for r in rs), default=0)
        cost = sum(float(r.get("cost") or 0) for r in rs)
        note = []
        if any(r.get("over_cap") for r in rs):
            note.append("OUTPUT EXCEEDED max_tokens")
        # tiny prompts are dominated by chat-template overhead: judge real ones only
        ratios = [r["in_est_ratio"] for r in rs if r.get("in_est_ratio")
                  and int(r.get("usage", {}).get("in", 0) or 0) >= 100]
        if ratios and (min(ratios) < 0.7 or max(ratios) > 1.5):
            note.append(f"input estimate off (est/actual {min(ratios)}..{max(ratios)})")
        if errs:
            note.append("errors: " + " | ".join(errs))
        lines.append(f"{m}: {ok}/{len(rs)} ok, via {'/'.join(via) or '-'}, "
                     f"reasoning tokens reported: {'yes' if reason else 'no'}, "
                     f"cost {cost:.0f}" + (" -- " + "; ".join(note) if note else ""))
    tool = [r for r in results if r["test"] == "tool"]
    if tool:
        lines.append("tool calling: " + ("works" if all(r.get("ok") for r in tool)
                                         else "FAILS on " + ", ".join(
                                             r["model"] for r in tool if not r.get("ok"))))
    raw = [r for r in results if r["transport_requested"] == "raw"]
    oj = [r for r in results if r["transport_requested"] == "openjiuwen"]
    if oj:
        lines.append("openJiuwen transport: " + (
            "works" if any(r.get("ok") and r["backend_used"] == "openjiuwen" for r in oj)
            else "FAILS (harness would fall back to raw HTTP)"))
    if raw:
        lines.append("raw HTTP transport: " + ("works" if all(r.get("ok") for r in raw)
                                               else "FAILS"))
    return lines


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "runs" / f"probe_{time.strftime('%Y%m%d_%H%M%S')}.json"))
    ap.add_argument("--budget", type=float, default=float(os.environ.get("PROBE_BUDGET", "8000")))
    ap.add_argument("--models", default=",".join(ALL_MODELS))
    a = ap.parse_args()
    if not os.environ.get("LLM_BASE_URL") or not os.environ.get("LLM_API_KEY"):
        print("Set LLM_BASE_URL and LLM_API_KEY first.")
        return 2
    try:
        import openjiuwen  # noqa: F401
        oj_version = getattr(openjiuwen, "__version__", "installed")
    except Exception as e:  # noqa: BLE001
        oj_version = f"NOT IMPORTABLE: {type(e).__name__}: {e}"[:200]
    led = BudgetLedger(total=a.budget)
    llm = LLM(led, max_concurrency=1)
    results = []
    models = [m for m in a.models.split(",") if m]
    plan = []
    for m in models:
        if "noreason" in m:
            plan += [(m, "openjiuwen", "hello"), (m, "raw", "hello"),
                     (m, "openjiuwen", "tool"), (m, "openjiuwen", "math")]
        else:  # thinking models are expensive: only what the harness uses them for
            plan += [(m, "openjiuwen", "hello"), (m, "openjiuwen", "math")]
    for m, tr, kind in plan:
        rec = await one(llm, led, m, tr, kind)
        results.append(rec)
        u = rec.get("usage", {})
        print(f"{m:26s} {tr:10s} {kind:5s} ok={str(rec.get('ok')):5s} "
              f"via={rec['backend_used']:10s} in={u.get('in','-'):>5} out={u.get('out','-'):>5} "
              f"reason={u.get('reason','-'):>5} cost={rec.get('cost','-'):>7} {rec['sec']}s "
              f"{rec.get('error','')[:80]}", flush=True)
        if led.dead:
            print("proxy reports budget exhausted - stopping")
            break
    summary = verdict(results, models)
    print("\nSUMMARY")
    for line in summary:
        print("  " + line)
    report = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"), "summary": summary,
        "python": sys.version.split()[0], "platform": platform.platform(),
        "openjiuwen": oj_version,
        "base_url_host": (os.environ.get("LLM_BASE_URL") or "").split("/")[2:3],
        "spent": round(led.spent, 1), "calls": led.calls, "results": results,
    }
    out = Path(a.out)
    if not out.is_absolute():
        out = _cwd / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nspent {led.spent:.0f} competition tokens in {led.calls} calls")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
