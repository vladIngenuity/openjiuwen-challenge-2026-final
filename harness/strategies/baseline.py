"""Baseline: the pre-contract harness policy expressed through the contract.

* order: pending tasks by reward * p / cost (desc); tasks a model already
  called infeasible go last.
* opt-in (HARNESS_CLAIMED_TASK_CAP > 0, off by default): a task some model
  called INFEASIBLE escalates only while > 30 % of the budget is left and
  under that total ceiling.
* attempt 1: cheap one-shot with the main no-reason model;
  attempt 2: second one-shot with the other no-reason model (coding: agent);
  attempt 3: tool agent (non-coding).
* verify: independent second opinion while > 35 % of the budget is left.
* never asks for diagnostics.
"""
from __future__ import annotations

import os

from ..llm import MODEL_FAST, MODEL_FAST_ALT, MODEL_REASON
from ..task_limits import TASK_CAP
from ..strategy import (AttemptResult, DET_MAYBE_INFEASIBLE, INFEASIBLE_CLAIMED, MIN_CAP,
                        PENDING, RunState, TaskView)

PRIOR_P = {"math": 0.85, "data_analysis": 0.8, "search": 0.85, "coding": 0.65}
PRIOR_C = {"math": 160, "data_analysis": 260, "search": 220, "coding": 700}


def _env_float(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, default))
    except ValueError:
        return default
    return v if v > 0 else default


AGENT_CAP = _env_float("HARNESS_AGENT_CAP", 1200.0)  # one escalated attempt
# Opt-in: a task some model already called INFEASIBLE (15-25 % of the final set
# are infeasible) escalates only from spare budget and under a lower total
# ceiling.  Off by default: the thresholds are not validated on real Qwen, and a
# false INFEASIBLE claim could cost a feasible high-reward task (review of #23).
CLAIMED_TASK_CAP = _env_float("HARNESS_CLAIMED_TASK_CAP", 0.0)   # e.g. 700; 0 = off
CLAIMED_MIN_ATTEMPT = 300.0   # below this an extra attempt cannot do real work
CLAIMED_SPARE_FRAC = 0.30     # escalate claimed tasks only while > 30 % is left


class Baseline:
    name = "baseline"
    verify_min_budget_frac = 0.35

    # ------------------------------------------------------------ estimates
    def p_success(self, t: TaskView, state: RunState) -> float:
        if t.est_p is not None:
            return t.est_p
        p = PRIOR_P.get(t.type, 0.5)
        s = state.type_stats.get(t.type)
        if t.type == "coding" and s and s.get("n"):
            p = (p * 2 + s.get("verified", 0)) / (2 + s["n"])
        if t.det_status == DET_MAYBE_INFEASIBLE:
            p *= 0.35
        return p

    def cost(self, t: TaskView, state: RunState) -> float:
        if t.est_cost is not None:
            return max(50.0, t.est_cost)
        c = PRIOR_C.get(t.type, 1500)
        if t.type == "coding" and t.files_bytes:
            c = 0.1 * (t.files_bytes + 2500) / 3 + 0.5 * t.files_bytes / 3 + 150
        s = state.type_stats.get(t.type)
        if s and s.get("n"):
            c = (c + s.get("cost", 0)) / (1 + s["n"])
        return max(50.0, c)

    @staticmethod
    def _llm_infeasible_claims(t: TaskView, state: RunState) -> int:
        return sum(1 for a in state.attempts(t.task_id) if a.status == INFEASIBLE_CLAIMED)

    def _claimed_limited(self, t: TaskView, state: RunState) -> bool:
        return CLAIMED_TASK_CAP > 0 and self._llm_infeasible_claims(t, state) >= 1

    @staticmethod
    def _spent_on(t: TaskView, state: RunState) -> float:
        return sum(a.cost for a in state.attempts(t.task_id))

    # -------------------------------------------------------------- contract
    def order(self, tasks: list[TaskView], state: RunState) -> list[str]:
        pend = [t for t in tasks if state.status_by_task.get(t.task_id, PENDING) == PENDING]
        pend.sort(key=lambda t: (self._llm_infeasible_claims(t, state),
                                 len(state.attempts(t.task_id)),
                                 -(t.reward * self.p_success(t, state) / self.cost(t, state))))
        return [t.task_id for t in pend]

    def budget_for(self, task: TaskView, state: RunState) -> float:
        n = len([a for a in state.attempts(task.task_id) if a.kind != "vote"])
        left = max(0.0, TASK_CAP - self._spent_on(task, state))
        if n == 0:
            need = self.cost(task, state)
            requested = need * 4 if state.remaining >= need * 0.6 else 0.0
            return min(requested, left)
        open_tasks = sum(1 for s in state.status_by_task.values() if s == PENDING)
        share = state.remaining / max(1, open_tasks)
        # The desired minimum (800) must never override the configured max.
        requested = min(max(800.0, share * 2.5), AGENT_CAP)
        if self._claimed_limited(task, state):
            # Opt-in (#23). Re-checked here, not only in should_escalate: other
            # workers may have spent the budget between the two calls.
            if state.remaining <= CLAIMED_SPARE_FRAC * state.budget_total:
                return 0.0
            claimed_left = CLAIMED_TASK_CAP - self._spent_on(task, state)
            if claimed_left < CLAIMED_MIN_ATTEMPT:
                return 0.0
            return min(requested, left, claimed_left)
        return min(requested, left)

    def model_for(self, task: TaskView, state: RunState, attempt: int) -> str:
        if attempt == 1:
            m = MODEL_FAST
        elif attempt == 2 and task.type != "coding":
            m = MODEL_FAST_ALT
        else:
            m = MODEL_FAST
        if m in state.unavailable_models:
            m = MODEL_FAST_ALT if m == MODEL_FAST else MODEL_FAST
        return m

    def should_escalate(self, task: TaskView, result: AttemptResult, state: RunState) -> bool:
        claims = self._llm_infeasible_claims(task, state)
        if claims >= 2:
            return False
        if claims >= 1 and task.det_status == DET_MAYBE_INFEASIBLE:
            return False
        if self._claimed_limited(task, state) and self.budget_for(task, state) < MIN_CAP:
            return False
        if TASK_CAP - self._spent_on(task, state) < MIN_CAP:
            return False
        max_attempts = 2 if task.type == "coding" else 3
        return result.attempt < max_attempts

    def should_verify(self, task: TaskView, result: AttemptResult, state: RunState) -> bool:
        return (task.type in ("math", "data_analysis", "search")
                and result.verify == "none"
                and state.remaining > self.verify_min_budget_frac * state.budget_total
                and state.time_left > 120)

    def should_diagnose(self, task: TaskView, state: RunState) -> bool:
        return False

    # vote models, used by the Executor for should_verify
    vote_models = (MODEL_FAST_ALT, MODEL_REASON)
    vote_cap = 600.0     # a second opinion must not cost more than the answer itself
