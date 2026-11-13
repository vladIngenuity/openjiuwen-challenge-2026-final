"""Opt-in Qwen global preflight then Baseline task ordering.

All Qwen calls are made by Executor.preflight_all, never in policy methods.
Preflight's estimated 0..10 solveability rating is an *uncalibrated hint*,
not a correctness oracle. Keep a floor to avoid excluding hard tasks.
"""
from __future__ import annotations

from ..strategy import PENDING, RunState, TaskView
from .baseline import Baseline


class QwenPreflight(Baseline):
    name = "qwen_preflight"
    preflight_enabled = True

    def order(self, tasks: list[TaskView], state: RunState) -> list[str]:
        pending = [t for t in tasks
                   if state.status_by_task.get(t.task_id, PENDING) == PENDING]
        def key(t):
            d = state.diagnostics.get(t.task_id, {})
            rating = d.get("preflight_score")
            if type(rating) is int and 0 <= rating <= 10:
                # Conservative: a preflight prediction can change priority
                # but cannot make any task ineligible.
                p = self.p_success(t, state) * (0.35 + 0.065 * rating)
            else:
                p = self.p_success(t, state)
            return (self._llm_infeasible_claims(t, state),
                    len([a for a in state.attempts(t.task_id)
                         if a.kind not in ("vote", "diagnose")]),
                    -(t.reward * p / self.cost(t, state)), t.task_id)
        pending.sort(key=key)
        return [t.task_id for t in pending]

