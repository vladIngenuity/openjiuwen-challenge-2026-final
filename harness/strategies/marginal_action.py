"""Experimental marginal-value action scheduling (AdaCompute / CoBa inspired).

This is NOT a reproduction of either paper and is NOT enabled by default.
Unlike Baseline's hard first-attempt-before-retry ordering, rank the
expected incremental reward / next-action cost across all pending tasks.
Calibration constants are hypotheses and require held-out real-Qwen tests.

Safety: inherit Baseline's retry, verification and budget decisions; the
Executor (stacked on PR #27) enforces aggregate task budgets.
"""
from __future__ import annotations

import math

from ..strategy import INFEASIBLE_CLAIMED, PENDING, RunState, TaskView
from .baseline import AGENT_CAP, Baseline


class MarginalAction(Baseline):
    name = "marginal_action"

    # Unverified failures imply the next attempt is less likely to succeed
    # than the first, but not zero; deliberately conservative hypotheses.
    RETRY_MULTIPLIER = 0.45
    CLAIM_MULTIPLIER = 0.20
    AGENT_COST_MULTIPLIER = 1.35

    def next_action(self, task: TaskView, state: RunState) -> tuple[float, float]:
        """Estimated *incremental* success probability and next-action cost.

        These values are prior-based, not measured conditional probabilities.
        Keep all scoring local to the Strategy, never to the Executor.
        """
        attempts = [a for a in state.attempts(task.task_id) if a.kind != "vote"]
        p = max(0.0, min(1.0, self.p_success(task, state)))
        cost = self.cost(task, state)
        for attempt in attempts:
            p *= (self.CLAIM_MULTIPLIER if attempt.status == INFEASIBLE_CLAIMED
                  else self.RETRY_MULTIPLIER)
        if attempts:
            cost = min(AGENT_CAP, max(50.0, cost * self.AGENT_COST_MULTIPLIER))
        return p, max(50.0, cost)

    def order(self, tasks: list[TaskView], state: RunState) -> list[str]:
        scored = []
        for t in tasks:
            if state.status_by_task.get(t.task_id, PENDING) != PENDING:
                continue
            p, next_cost = self.next_action(t, state)
            expected_gain = max(0.0, t.reward) * p
            # Marginal reward per expected cost; avoids treating a retry
            # as equally valuable as a first try.
            score = expected_gain / next_cost if next_cost > 0 else 0.0
            if not math.isfinite(score):
                score = 0.0
            scored.append((-score, -expected_gain, t.task_id))
        scored.sort()
        return [task_id for _, _, task_id in scored]
