"""Batch Qwen preflight of all currently pending tasks, before solving any.

Read-only diagnostics, never hidden answers. Reports concise 0..10 feasibility
of getting a *correct solution* with the current models, NOT a proof that a
task is feasible. The ratings cannot justify hard skipping or INFEASIBLE.

Hard plan cap: at most 20% of usable run budget or 2000 contest units. The
global ledger is authoritative. If a batch cannot fit, leave the remaining
tasks at Baseline priors. Every batch is made before solving begins.

This is intentionally a single-pass, one-shot experimental preflight; no
tool calls, no samples of the full workspace, no claims of calibration.
"""
from __future__ import annotations

import json
import math
import re

from .llm import LLMUnavailable, MODEL_FAST, cap_scope
from .log import log


def parse_ratings(content: str, count: int) -> list[int] | None:
    """Accept only an exact compact JSON array of integer ratings 0..10."""
    if count <= 0:
        return None
    s = (content or "").strip()
    try:
        value = json.loads(s)
    except (ValueError, TypeError):
        match = re.search(r"\[[^\[\]]*\]", s)
        if not match:
            return None
        try:
            value = json.loads(match.group())
        except ValueError:
            return None
    if not isinstance(value, list) or len(value) != count:
        return None
    if any(type(x) is not int or not 0 <= x <= 10 for x in value):
        return None
    return value


def make_batch(tasks) -> tuple[list[dict], list[str]]:
    """Small inexpensive metadata snapshot only; prompt doesn't expose truth."""
    rows, ids = [], []
    for t in tasks:
        ids.append(t.task_id)
        rows.append({
            "id": t.task_id, "category": t.type,
            "reward": round(float(t.reward), 2),
            "instruction": str(t.instruction)[:160],
            "files": int(t.n_files), "bytes": int(t.files_bytes),
            "det": t.det_status,
        })
    return rows, ids


async def preflight_all(executor, *, max_fraction: float = 0.20,
                        max_total: float = 2000.0,
                        batch_size: int = 10) -> dict[str, dict]:
    h = executor.h
    tasks = [t for t in h.tasks if t.status == "pending"]
    if not tasks or not h.llm.enabled:
        return {}
    if h.time_left() < 180:
        return {}
    views = [executor.view(t) for t in tasks]
    global_cap = min(max_total, max(0.0, h.ledger.usable()) * max_fraction)
    remaining_cap = global_cap
    diagnostics = {}
    for first in range(0, len(views), batch_size):
        chunk = views[first:first+batch_size]
        if h.time_left() < 150 or remaining_cap < 50:
            break
        # Distribute remaining cap over remaining batches. Each batch gets
        # at least 50 units only if a reservation can actually be made.
        batches_left = math.ceil((len(views)-first)/batch_size)
        cap = remaining_cap / batches_left
        if cap < 50:
            break
        task_objs = tasks[first:first+batch_size]
        rows = [{
            "id": i, "kind": v.type,
            "reward": round(v.reward, 1),
            "prompt": t.instruction[:135],
            "files": v.n_files, "bytes": v.files_bytes,
            "det": v.det_status,
        } for i,(t,v) in enumerate(zip(task_objs,chunk))]
        prompt = (
            "Estimate the chance (0=no chance, 10=very likely) that an AI agent "
            "will CORRECTLY solve each of these tasks under a strict token "
            "budget. Use task content and available file metadata only; "
            "actual file contents are NOT supplied. Do not solve tasks. "
            "Do not mark tasks infeasible. Return exactly a JSON array of "
            f"{len(rows)} integers, e.g. [5,7,2]. No explanation.\n"
            + json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        )
        try:
            with cap_scope(cap):
                response = await h.llm.chat(
                    [{"role": "user", "content": prompt}],
                    model=MODEL_FAST, max_tokens=100,
                    tag=f"preflight:{first//batch_size}",
                )
            ratings = parse_ratings(response.get("content", ""), len(chunk))
        except LLMUnavailable as e:
            log(f"preflight batch {first//batch_size}: {e}")
            ratings = None
        # Charged costs, including unsuccessful proxy requests, appear in
        # the central ledger. Never manufacture a free diagnostic.
        spent_preflight = sum(float(c.get("cost", 0)) for c in h.ledger.log
                              if str(c.get("tag", "")).startswith("preflight:"))
        remaining_cap = max(0.0, global_cap - spent_preflight)
        if ratings is None:
            log(f"preflight batch {first//batch_size}: invalid response")
            continue
        for view, rating in zip(chunk, ratings):
            diagnostics[view.task_id] = {"preflight_score": rating,
                                         "preflight_model": MODEL_FAST}
    log(f"preflight: rated {len(diagnostics)}/{len(views)} pending tasks "
        f"for {global_cap-remaining_cap:.0f} contest units")
    return diagnostics
