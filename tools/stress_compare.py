#!/usr/bin/env python3
"""Calibrate a *scheduler-only* stress budget on random, then evaluate holdout.

This is a synthetic mock experiment, NOT a measurement of real Qwen quality.
Free deterministic solvers are deliberately disabled by two explicit env flags
for stress benchmarking; the production default is unchanged.

Calibration chooses B using only random on separate seeds (not baseline/ML).
The test seeds and strategy outputs are never used to select B. A target band
is descriptive, not a guarantee: unachieved calibration is explicitly reported.

Examples:
  python tools/stress_compare.py --cal-seeds 101,102 --test-seeds 201,202,203
  python tools/stress_compare.py --n 60 --budgets 300,600,1200,2400,4800
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
STRATEGIES = "random,baseline,marginal_action,online_calibration"


def run_compare(*, seeds: str, n: int, budget: float, noise: float,
                infeasible: float, strategies: str, out: Path) -> dict:
    env = os.environ.copy()
    env["HARNESS_BENCHMARK_STRESS"] = "1"
    env["HARNESS_STRESS_SKIP_DETERMINISTIC"] = "1"
    env["HARNESS_TIME_LIMIT"] = "900"
    cmd = [sys.executable, str(ROOT / "tools" / "compare.py"),
           "--seeds", seeds, "--n", str(n),
           "--infeasible", str(infeasible), "--mode", "mock",
           "--noise", str(noise), "--budget", str(budget),
           "--strategies", strategies, "--out", str(out)]
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                            text=True, timeout=900)
    print(result.stdout, flush=True)
    if result.returncode:
        print(result.stderr[-4000:], file=sys.stderr)
        raise RuntimeError(f"compare.py failed with rc={result.returncode}")
    payload = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    if any(row.get("rc", 1) for row in payload["runs"]):
        raise RuntimeError("Harness failed in one or more episodes")
    return payload


def total_pct(rows: list[dict]) -> float:
    max_reward = sum(row["max"] for row in rows)
    return 100 * sum(row["score"] for row in rows) / max_reward if max_reward else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cal-seeds", default="101,102")
    ap.add_argument("--test-seeds", default="201,202,203")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--budgets", default="300,600,1200,2400,4800,7200")
    ap.add_argument("--noise", type=float, default=0.25)
    ap.add_argument("--infeasible", type=float, default=0.25)
    ap.add_argument("--target", type=float, default=50.0,
                    help="calibration target for random reward percent")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cal = [int(s) for s in a.cal_seeds.split(",") if s]
    test = [int(s) for s in a.test_seeds.split(",") if s]
    budgets = sorted({float(s) for s in a.budgets.split(",") if s})
    if not cal or not test or set(cal) & set(test):
        ap.error("calibration and test seeds must be non-empty and disjoint")
    if a.n < 4 or not budgets or min(budgets) < 50 or max(budgets) > 100000:
        ap.error("invalid n or candidate budgets")
    if not (0 <= a.noise < 1 and 0 <= a.infeasible < 1
            and 0 <= a.target <= 100):
        ap.error("invalid noise, infeasible or target")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = Path(a.out) if a.out else (ROOT / "docs" / "research" / "mock" /
                                      f"stress_{stamp}.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="stress_cal_") as tmp:
        tmpdir = Path(tmp)
        calibration = []
        for i, budget in enumerate(budgets):
            print(f"CALIBRATION budget={budget:g}", flush=True)
            report = run_compare(
                seeds=a.cal_seeds, n=a.n, budget=budget, noise=a.noise,
                infeasible=a.infeasible, strategies="random",
                out=tmpdir / f"cal_{i}.md")
            pct = total_pct(report["runs"])
            calibration.append({"budget": budget, "random_pct": round(pct, 3)})
        chosen = min(calibration, key=lambda x: (abs(x["random_pct"]-a.target),
                                                 x["budget"]))
        print(f"SELECTED budget={chosen['budget']:g}, calibration random="
              f"{chosen['random_pct']:.2f}% (target={a.target:.1f}%)", flush=True)
        test_report = run_compare(
            seeds=a.test_seeds, n=a.n, budget=chosen["budget"],
            noise=a.noise, infeasible=a.infeasible, strategies=STRATEGIES,
            out=tmpdir / "holdout.md")

    grouped = {}
    for st in STRATEGIES.split(","):
        runs = [r for r in test_report["runs"] if r["strategy"] == st]
        grouped[st] = {
            "reward_pct": round(total_pct(runs), 3),
            "reward": sum(r["score"] for r in runs),
            "max_reward": sum(r["max"] for r in runs),
            "mean_spent": round(sum(r["spent"] for r in runs) / len(runs), 1),
            "mean_calls": round(sum(r["calls"] for r in runs) / len(runs), 1),
            "wrong": sum(r["wrong"] for r in runs),
        }
    payload = {
        "method": "mock scheduler-only stress; deterministic solvers disabled",
        "caveats": ["Mock has ground truth; not real Qwen accuracy.",
                    "Budget calibrated only on random, disjoint calibration seeds.",
                    "Target score is not guaranteed on heldout seeds.",
                    "Template families overlap across seeds.",
                    "Correctness is scored on feasible reward only."],
        "config": vars(a),
        "calibration": calibration,
        "selected_budget": chosen["budget"],
        "test_aggregate": grouped,
        "test_runs": test_report["runs"],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\nHOLDOUT results (mock only):")
    for st, v in grouped.items():
        print(f"  {st:20s}: reward={v['reward_pct']:6.2f}% "
              f"spent={v['mean_spent']:7.1f} calls={v['mean_calls']:5.1f}")
    print("Report:", out)
    if not 40 <= chosen["random_pct"] <= 60:
        print("WARNING: Random did not reach 40–60% on calibration; "
              "expand --budgets instead of assuming target was achieved.")


if __name__ == "__main__":
    main()
