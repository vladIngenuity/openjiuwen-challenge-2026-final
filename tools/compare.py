#!/usr/bin/env python3
"""Compare strategies on identical tasks and budget.

    # mock LLM (safe, free):
    python tools/compare.py --strategies baseline,legacy --seeds 1,2,3 --mode mock
    # real Qwen (spends tokens! needs LLM_BASE_URL / LLM_API_KEY):
    python tools/compare.py --strategies baseline --seeds 7 --n 40 --mode real --budget 20000

Each seed generates one task set with Task Factory (ground truth kept outside
the task dirs); every strategy runs on its own fresh copy of that set with the
same budget.  Results go to docs/research/<mode>/compare_<timestamp>.md (+ .json);
mock / real / sim results are never mixed in one file.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from evaluate import score  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_one(strategy, tasks_dir: Path, truth: Path, mode: str, budget: float, noise: float,
            seed: int, workdir: Path) -> dict:
    env = {k: v for k, v in os.environ.items()}
    env["BUDGET"] = str(budget)
    env["HARNESS_RANDOM_SEED"] = str(seed)
    env["HARNESS_TRACE"] = str(workdir / f"trace_{strategy}.json")
    mock = None
    if mode == "mock":
        port = free_port()
        mock = subprocess.Popen([sys.executable, str(ROOT / "tools" / "mock_llm.py"), str(truth),
                                 "--port", str(port), "--budget", str(budget),
                                 "--noise", str(noise), "--seed", str(seed)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Task indexing may take more than 0.8s on CI; wait for the listener.
        deadline = time.monotonic() + 20
        while True:
            if mock.poll() is not None:
                raise RuntimeError("mock server exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    mock.terminate()
                    raise RuntimeError("mock server startup timed out")
                time.sleep(0.1)
        env["LLM_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
        env["LLM_API_KEY"] = "mock"
    elif not env.get("LLM_BASE_URL"):
        raise SystemExit("--mode real needs LLM_BASE_URL and LLM_API_KEY")
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, str(ROOT / "run_agent.py"), "--tasks-dir",
                            str(tasks_dir), "--strategy", strategy], env=env,
                           capture_output=True, text=True, timeout=3600)
    finally:
        if mock:
            mock.terminate()
            mock.wait(timeout=5)
    sec = time.time() - t0
    res = score(tasks_dir, truth)
    tr = {}
    try:
        tr = json.loads(Path(env["HARNESS_TRACE"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    calls = tr.get("calls", [])
    res.update({
        "strategy": strategy, "seed": seed, "rc": p.returncode, "sec": round(sec, 1),
        "spent": round(tr.get("spent", 0.0), 1), "calls": len(calls),
        "plan_cost": round(sum(c.get("cost", 0) for c in calls
                               if str(c.get("tag", "")).startswith(("plan:", "preflight:"))), 1),
        "oj_share": round(sum(1 for c in calls if c.get("transport") == "openjiuwen")
                          / max(1, sum(1 for c in calls if not c.get("error"))), 2),
    })
    if p.returncode != 0:
        res["stderr_tail"] = p.stderr[-800:]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategies", default="baseline,legacy")
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--infeasible", type=float, default=0.2)
    ap.add_argument("--mode", choices=["mock", "real"], default="mock")
    ap.add_argument("--budget", type=float, default=100000)
    ap.add_argument("--noise", type=float, default=0.15, help="mock only: wrong-answer rate")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    strategies = [s for s in a.strategies.split(",") if s]
    seeds = [int(x) for x in a.seeds.split(",") if x]
    work = Path(tempfile.mkdtemp(prefix="compare_"))
    rows = []
    for seed in seeds:
        base = work / f"seed{seed}"
        subprocess.run([sys.executable, str(ROOT / "tools" / "task_factory.py"), str(base),
                        "--n", str(a.n), "--seed", str(seed), "--infeasible", str(a.infeasible)],
                       check=True, capture_output=True)
        truth = base.parent / f"{base.name}_truth.json"
        for st in strategies:
            d = work / f"seed{seed}_{st}"
            shutil.copytree(base, d)
            t_copy = work / f"seed{seed}_{st}_truth.json"
            shutil.copy(truth, t_copy)
            r = run_one(st, d, t_copy, a.mode, a.budget, a.noise, seed, work)
            rows.append(r)
            print(f"seed={seed} {st:10s} score={r['score']:g}/{r['max']:g} wrong={r['wrong']} "
                  f"ans_infeasible={r['answered_infeasible']} spent={r['spent']:.0f} "
                  f"calls={r['calls']} plan={r['plan_cost']:.0f} {r['sec']}s rc={r['rc']}",
                  flush=True)
    # aggregate
    agg = {}
    for st in strategies:
        rs = [r for r in rows if r["strategy"] == st]
        agg[st] = {
            "score_pct": round(100 * sum(r["score"] for r in rs) / max(1, sum(r["max"] for r in rs)), 2),
            "wrong": sum(r["wrong"] for r in rs),
            "answered_infeasible": sum(r["answered_infeasible"] for r in rs),
            "spent_avg": round(sum(r["spent"] for r in rs) / len(rs), 1),
            "plan_avg": round(sum(r["plan_cost"] for r in rs) / len(rs), 1),
            "sec_avg": round(sum(r["sec"] for r in rs) / len(rs), 1),
        }
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = Path(a.out) if a.out else ROOT / "docs" / "research" / a.mode / f"compare_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Сравнение стратегий ({a.mode})", "",
             f"Дата: {time.strftime('%Y-%m-%d %H:%M')}. Наборы Task Factory: seeds={seeds}, "
             f"n={a.n}, доля невыполнимых {a.infeasible}. Бюджет {a.budget:g}."
             + (f" Mock-шум {a.noise}." if a.mode == "mock" else " Реальный прокси."), "",
             "| стратегия | % достижимых баллов | неверных | ответов на невыполнимые | токенов (ср.) | из них планирование | сек (ср.) |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for st, g in agg.items():
        lines.append(f"| {st} | {g['score_pct']} | {g['wrong']} | {g['answered_infeasible']} | "
                     f"{g['spent_avg']} | {g['plan_avg']} | {g['sec_avg']} |")
    lines += ["", "Подробно по запускам — в соседнем .json."]
    if a.mode == "mock":
        lines += ["", "**Внимание:** это mock-LLM, а не реальный Qwen; выводы о реальном расходе "
                      "токенов отсюда делать нельзя."]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({"args": vars(a), "aggregate": agg,
                                                    "runs": rows}, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print("\n".join(lines))
    print(f"\nreport: {out}")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
