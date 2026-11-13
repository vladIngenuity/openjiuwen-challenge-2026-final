"""Evidence-based model routing from paired development trajectories.

The paired benchmark320 runs support Reason for Math/Coding and Fast for
Search/Data Analysis. This policy deliberately stays small: one category
router, measured cost/success priors, no immediate voting, and no scheduler
retry. Once the first pass is complete, surplus budget may fund ranked
independent verification while preserving a fixed reserve.
Local execution feedback may still justify the bounded repair implemented by
``ReasonFirstBounded``. The constants are development priors, not hidden-test
claims, and should be replaced only by a new independent paired experiment.
"""
from __future__ import annotations

from ..llm import (MODEL_FAST, MODEL_FAST_ALT, MODEL_REASON,
                   MODEL_REASON_ALT)
from ..strategy import PENDING, RunState, TaskView
from ..task_limits import TASK_CAP
from .reason_first_bounded import ReasonFirstBounded


class EmpiricalHybrid(ReasonFirstBounded):
    name = "empirical_hybrid"
    # Endgame is an Executor opt-in extension: it runs only after every first
    # attempt has reached a final status. The ledger's own safety reserve is
    # additional to this amount.
    endgame_enabled = True
    endgame_reserve = 5000.0
    endgame_min_time = 240.0
    endgame_vote_cap = 900.0
    # Both differ from the primary models used by this router. On disagreement
    # the answer changes only if two of the three candidates agree.
    vote_models = (MODEL_FAST_ALT, MODEL_REASON_ALT)

    # Rewarded local correctness per task on the 272-task paired development
    # support. Impossible-task recognition is useful for saving cost but does
    # not receive reward in these priors.
    SUCCESS_PRIOR = {
        "math": 0.70,
        "search": 0.72,
        "data_analysis": 0.74,
        "coding": 0.40,
    }
    # Observed mean total task costs. They intentionally include the older
    # strategy's extra calls, making ordering conservative for this bounded
    # policy rather than pretending a single-call estimate is exact.
    COST_PRIOR = {
        "math": 650.0,
        "search": 45.0,
        "data_analysis": 525.0,
        "coding": 590.0,
    }
    # Reservation caps allow conservative input estimates plus the requested
    # output. Executor and BudgetLedger still enforce aggregate/global limits.
    FIRST_CAP = {
        "math": 1400.0,
        "search": 500.0,
        "data_analysis": 1300.0,
        "coding": 1500.0,
    }
    REASON_TYPES = frozenset({"math", "coding"})

    def p_success(self, task: TaskView, state: RunState) -> float:
        return self.SUCCESS_PRIOR.get(task.type, 0.35)

    def cost(self, task: TaskView, state: RunState) -> float:
        return self.COST_PRIOR.get(task.type, 900.0)

    def order(self, tasks: list[TaskView], state: RunState) -> list[str]:
        pending = [
            task for task in tasks
            if state.status_by_task.get(task.task_id, PENDING) == PENDING
        ]
        pending.sort(
            key=lambda task: (
                -(max(0.0, task.reward) * self.p_success(task, state)
                  / self.cost(task, state)),
                -max(0.0, task.reward),
                task.task_id,
            )
        )
        return [task.task_id for task in pending]

    def budget_for(self, task: TaskView, state: RunState) -> float:
        left = max(0.0, TASK_CAP - self._spent_on(task, state))
        return min(self.FIRST_CAP.get(task.type, 1000.0), left,
                   max(0.0, state.remaining))

    def model_for(self, task: TaskView, state: RunState, attempt: int) -> str:
        if task.type in self.REASON_TYPES:
            return (MODEL_REASON_ALT if MODEL_REASON in state.unavailable_models
                    else MODEL_REASON)
        return (MODEL_FAST_ALT if MODEL_FAST in state.unavailable_models
                else MODEL_FAST)

    def endgame_order(self, tasks: list[TaskView], state: RunState) -> list[str]:
        """Highest expected correction value per unit of verification first."""
        candidates = [
            task for task in tasks
            if task.reward > 0 and task.type in ("math", "search", "data_analysis")
        ]
        candidates.sort(
            key=lambda task: (
                -(task.reward * (1.0 - self.p_success(task, state))
                  / self.cost(task, state)),
                -task.reward,
                task.task_id,
            )
        )
        return [task.task_id for task in candidates]
