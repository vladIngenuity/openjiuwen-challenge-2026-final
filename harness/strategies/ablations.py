"""Ablation variants for the marginal-action family.

Keep every other Baseline/Executor setting identical. Coefficients are
pre-registered experimental values; do NOT tune on test-seed outcomes.
"""
from __future__ import annotations

from .marginal_action import MarginalAction
from .online_calibration import OnlineCalibration


class MarginalNoPenalty(MarginalAction):
    name = "marginal_no_penalty"
    RETRY_MULTIPLIER = 1.0
    CLAIM_MULTIPLIER = 1.0


class MarginalSoftPenalty(MarginalAction):
    name = "marginal_soft_penalty"
    RETRY_MULTIPLIER = 0.8
    CLAIM_MULTIPLIER = 0.5


class OnlineCostOnly(OnlineCalibration):
    """Learn request cost; retain prior predicted reward probabilities."""
    name = "online_cost_only"

    def next_action(self, task, state):
        _, learned_cost = super().next_action(task, state)
        prior_p, _ = MarginalAction.next_action(self, task, state)
        return prior_p, learned_cost
