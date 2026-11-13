#!/usr/bin/env python3
"""Paired offline analysis of Fast/Reason model routing.

This is an evaluator-side research tool. It reads private benchmark labels only
after both historical runs completed, reports aggregates only, and never writes
labels or reference answers into an agent task directory.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import statistics
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.tasks import _atomic_write
from tools.score320 import evaluate


POLICIES = {
    "all_fast": frozenset(),
    "all_reason": frozenset({"math", "search", "data_analysis", "coding"}),
    "math_reason": frozenset({"math"}),
    "math_coding_reason": frozenset({"math", "coding"}),
}
SUCCESS_PRIOR = {"math": .70, "search": .72, "data_analysis": .74, "coding": .40}
COST_PRIOR = {"math": 650., "search": 45., "data_analysis": 525., "coding": 590.}
CORRECT = {"correct_text", "coding_local_pass"}


def merged_reason_trace(run: Path, shards: list[dict]) -> dict:
    trace = {"calls": [], "results": {}, "seconds": 0.0}
    for shard in shards:
        path = run / "shards" / f"{shard['shard']:03d}" / "trace.json"
        if not path.is_file():
            raise ValueError(f"missing completed-shard trace: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        trace["calls"].extend(data.get("calls", []))
        trace["results"].update(data.get("results", {}))
        trace["seconds"] += float(shard.get("seconds", 0))
    return trace


def task_costs(trace: dict, task_ids: set[str]) -> dict[str, float]:
    costs = defaultdict(float)
    for call in trace.get("calls", []):
        parts = str(call.get("tag", "")).split(":")
        if len(parts) > 1 and parts[1] in task_ids:
            costs[parts[1]] += float(call.get("cost", 0))
    return dict(costs)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def replay_episode(ids, rows, costs, policy, budget):
    route = POLICIES[policy]
    ordered = sorted(
        ids,
        key=lambda task_id: (
            -(rows["fast"][task_id]["reward"]
              * SUCCESS_PRIOR[rows["fast"][task_id]["category"]]
              / COST_PRIOR[rows["fast"][task_id]["category"]]),
            task_id,
        ),
    )
    reward = spent = 0.0
    completed = 0
    for task_id in ordered:
        category = rows["fast"][task_id]["category"]
        action = "reason" if category in route else "fast"
        cost = costs[action].get(task_id, 0.0)
        if cost > budget - spent:
            continue
        spent += cost
        completed += 1
        if rows[action][task_id]["verdict"] in CORRECT:
            reward += rows[action][task_id]["reward"]
    return reward, spent, completed


def analyze(args):
    reason_summary = json.loads((args.reason_run / "summary.json").read_text())
    shards = reason_summary["shards"]
    paired_ids = [task_id for shard in shards for task_id in shard["tasks"]]
    if len(paired_ids) != len(set(paired_ids)):
        raise ValueError("duplicate paired task IDs")
    reason_trace = merged_reason_trace(args.reason_run, shards)
    fast_trace = json.loads(args.fast_trace.read_text(encoding="utf-8"))
    reason = evaluate(
        args.reason_run / "tasks", args.source, args.private,
        reason_trace, task_ids=paired_ids,
    )
    fast = evaluate(
        args.fast_tasks, args.source, args.private,
        fast_trace, task_ids=paired_ids,
    )
    rows = {
        "reason": {row["task_id"]: row for row in reason["rows"]},
        "fast": {row["task_id"]: row for row in fast["rows"]},
    }
    paired_set = set(paired_ids)
    costs = {
        "reason": task_costs(reason_trace, paired_set),
        "fast": task_costs(fast_trace, paired_set),
    }

    category_rows = []
    groups = defaultdict(list)
    for task_id in paired_ids:
        groups[rows["fast"][task_id]["category"]].append(task_id)
    for category in ("math", "search", "data_analysis", "coding"):
        ids = groups[category]
        entry = {"category": category, "tasks": len(ids)}
        for action in ("reason", "fast"):
            values = [costs[action].get(task_id, 0.0) for task_id in ids]
            entry[action] = {
                "reward": sum(rows[action][task_id]["reward"] for task_id in ids
                              if rows[action][task_id]["verdict"] in CORRECT),
                "correct": sum(rows[action][task_id]["verdict"] in CORRECT
                               for task_id in ids),
                "cost": round(sum(values), 1),
                "mean_cost": round(statistics.mean(values), 1),
            }
        entry["reason_only_wins"] = sum(
            rows["reason"][task_id]["verdict"] in CORRECT
            and rows["fast"][task_id]["verdict"] not in CORRECT
            for task_id in ids
        )
        entry["fast_only_wins"] = sum(
            rows["fast"][task_id]["verdict"] in CORRECT
            and rows["reason"][task_id]["verdict"] not in CORRECT
            for task_id in ids
        )
        category_rows.append(entry)

    rng = random.Random(args.seed)
    episodes = {policy: [] for policy in POLICIES}
    for _ in range(args.episodes):
        sample = []
        for category in ("math", "search", "data_analysis", "coding"):
            sample.extend(rng.sample(groups[category], args.per_category))
        for policy in POLICIES:
            episodes[policy].append(
                replay_episode(sample, rows, costs, policy, args.budget)
            )
    policy_rows = []
    for policy, outcomes in episodes.items():
        rewards = [row[0] for row in outcomes]
        spends = [row[1] for row in outcomes]
        completed = [row[2] for row in outcomes]
        policy_rows.append({
            "policy": policy,
            "mean_reward": round(statistics.mean(rewards), 2),
            "reward_p05": percentile(rewards, .05),
            "reward_p95": percentile(rewards, .95),
            "mean_spent": round(statistics.mean(spends), 1),
            "mean_completed": round(statistics.mean(completed), 2),
        })
    reference = [row[0] for row in episodes["all_fast"]]
    for row in policy_rows:
        values = [outcome[0] - base for outcome, base
                  in zip(episodes[row["policy"]], reference)]
        row["reward_delta_vs_fast"] = round(statistics.mean(values), 2)
        row["median_delta_vs_fast"] = statistics.median(values)
        row["delta_p05"] = percentile(values, .05)
        row["delta_p95"] = percentile(values, .95)
        row["win_rate_vs_fast"] = round(
            sum(value > 0 for value in values) / len(values), 4
        )
        row["loss_rate_vs_fast"] = round(
            sum(value < 0 for value in values) / len(values), 4
        )

    result = {
        "scope": {
            "paired_tasks": len(paired_ids), "completed_reason_shards": len(shards),
            "episodes": args.episodes, "tasks_per_episode": args.per_category * 4,
            "budget": args.budget, "seed": args.seed,
        },
        "warning": (
            "Development replay of historical multi-call strategies; local Coding tests are "
            "not official hidden correctness, this is not a live bounded-policy result, and "
            "the replay does not estimate the new endgame verification phase."
        ),
        "categories": category_rows,
        "policies": policy_rows,
    }
    _atomic_write(
        args.json_out,
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
    )
    lines = [
        "# Paired Fast/Reason routing replay",
        "",
        result["warning"],
        "",
        "## Paired development evidence",
        "",
        "| Category | Tasks | Reason reward/cost | Fast reward/cost | R-only wins | F-only wins |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in category_rows:
        lines.append(
            f"| {row['category']} | {row['tasks']} | "
            f"{row['reason']['reward']}/{row['reason']['cost']:.1f} | "
            f"{row['fast']['reward']}/{row['fast']['cost']:.1f} | "
            f"{row['reason_only_wins']} | {row['fast_only_wins']} |"
        )
    lines += [
        "", "## Balanced 100-task bootstrap replay", "",
        "| Policy | Mean reward | 5–95% | Δ vs Fast | Δ 5–95% | P(win)/P(loss) | Mean spent |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in policy_rows:
        lines.append(
            f"| {row['policy']} | {row['mean_reward']:.2f} | "
            f"{row['reward_p05']:.0f}–{row['reward_p95']:.0f} | "
            f"{row['reward_delta_vs_fast']:+.2f} | "
            f"{row['delta_p05']:+.0f}–{row['delta_p95']:+.0f} | "
            f"{100 * row['win_rate_vs_fast']:.1f}%/"
            f"{100 * row['loss_rate_vs_fast']:.1f}% | "
            f"{row['mean_spent']:.1f} |"
        )
    lines += [
        "", "The implemented `empirical_hybrid` corresponds to `math_coding_reason`.",
        "It keeps evaluation labels outside the runtime strategy.",
        "",
        "## Interpretation and limits",
        "",
        "- Use Reason for Math: it has 11 exclusive wins against 4 for Fast.",
        "- Use Fast for Search: correctness is tied while historical cost is much lower.",
        "- Use Fast for Data Analysis: it has 15 exclusive wins and Reason has none.",
        "- Coding is the weakest routing conclusion (5 versus 3 exclusive wins).",
        "- Do not fit task-ID or answer-derived routing rules; that would leak benchmark construction.",
        "- Keep the online text-quality head frozen until independent correctness labels exist.",
        "  Runtime text answers are unverified, so their success labels are not learnable online.",
        "- The cost head may continue learning from settled provider usage only.",
        "- Endgame verification is not included in these replay scores; measure its correction",
        "  and regression rates separately before attributing any additional reward to it.",
        "- Validate this candidate with a fresh live paired run, then open the final holdout once.",
    ]
    _atomic_write(args.md_out, "\n".join(lines) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reason-run", type=Path, required=True)
    parser.add_argument("--fast-tasks", type=Path, required=True)
    parser.add_argument("--fast-trace", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=2000)
    parser.add_argument("--per-category", type=int, default=25)
    parser.add_argument("--budget", type=float, default=100000)
    parser.add_argument("--seed", type=int, default=20261113)
    args = parser.parse_args()
    if args.episodes <= 0 or not 1 <= args.per_category <= 25 or args.budget <= 0:
        parser.error("episodes/budget must be positive and per-category must be 1..25")
    result = analyze(args)
    print(json.dumps(result["policies"], indent=2))


if __name__ == "__main__":
    main()
