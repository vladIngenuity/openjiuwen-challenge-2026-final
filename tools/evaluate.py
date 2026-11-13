#!/usr/bin/env python3
"""Score a harness run against Task Factory ground truth.

    python tools/evaluate.py TASKS_DIR [TRUTH_JSON]
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.sandbox import copy_inputs, run_suite


def score(tasks: Path, truth_path: Path) -> dict:
    """Machine-readable result for tools/compare.py."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = _evaluate(tasks, truth_path)
    return res


def main():
    tasks = Path(sys.argv[1])
    truth_path = Path(sys.argv[2]) if len(sys.argv) > 2 else tasks.parent / f"{tasks.name}_truth.json"
    _evaluate(tasks, truth_path)


def _evaluate(tasks: Path, truth_path: Path) -> dict:
    truth = json.loads(truth_path.read_text())
    per = defaultdict(lambda: defaultdict(float))
    wrong = []
    score = maxscore = 0
    for tid, tr in sorted(truth.items()):
        if Path(tid).name != tid or tid in {"", ".", ".."}:
            raise ValueError(f"invalid task ID: {tid!r}")
        d = tasks / tid
        if d.is_symlink():
            raise ValueError(f"symlinked task: {tid!r}")
        ans_f = d / "answer.txt"
        has = ans_f.is_file() and not ans_f.is_symlink()
        ans = ans_f.read_text(encoding="utf-8", errors="replace").strip() if has else None
        ty = tr["type"]
        p = per[ty]
        p["n"] += 1
        if not tr["feasible"]:
            p["infeasible"] += 1
            if not has:
                p["inf_skipped"] += 1
            else:
                wrong.append((tid, "answered infeasible"))
            continue
        maxscore += tr["reward"]
        ok = False
        if ty == "coding":
            ws = d / "workspace"
            if not ws.is_dir():
                ws = d
            has = ws.is_dir()
            if has:
                try:
                    with tempfile.TemporaryDirectory(prefix="grade-") as tmp:
                        stage = Path(tmp)
                        copy_inputs(ws, stage)
                        ok, _ = run_suite(stage, None, hidden_source=tr["_hidden"])
                except (OSError, ValueError, KeyError):
                    ok = False
                if not ok:
                    wrong.append((tid, "hidden tests failed"))
        else:
            ok = has and ans == tr["expected"]
            if has and not ok:
                wrong.append((tid, "answer differs"))
        if not has:
            p["unanswered_feasible"] += 1
        if ok:
            p["ok"] += 1
            score += tr["reward"]
            p["reward"] += tr["reward"]
    print(f"{'type':14s} {'n':>4s} {'ok':>4s} {'inf':>4s} {'inf_skip':>8s} {'miss':>5s}")
    for ty, p in sorted(per.items()):
        print(f"{ty:14s} {p['n']:4.0f} {p['ok']:4.0f} {p['infeasible']:4.0f} "
              f"{p['inf_skipped']:8.0f} {p['unanswered_feasible']:5.0f}")
    print(f"SCORE {score:g} / {maxscore:g} feasible reward")
    for w in wrong[:40]:
        print("  ✘", *w)
    n_inf = sum(p["infeasible"] for p in per.values())
    return {"score": score, "max": maxscore,
            "wrong": sum(1 for w in wrong if w[1] != "answered infeasible"),
            "answered_infeasible": sum(1 for w in wrong if w[1] == "answered infeasible"),
            "infeasible": n_inf,
            "per_type": {k: dict(v) for k, v in per.items()}}


if __name__ == "__main__":
    main()
