"""Opt-in online Bayesian calibration for marginal-action scheduling.

No Qwen fine-tuning and no extra inference calls. The strategy consumes the
Executor's existing RunState.history; all learning is deterministic and local.
Only test-verified coding outcomes are treated as correctness labels.
Unknown correctness of text answers MUST NOT become a training label.

The estimates are shrinkage posterior heuristics, not a proof of
calibration or a reproduction of AdaCompute / CoBa. Keep baseline as default.
"""
from __future__ import annotations

import math

from ..strategy import FAILED, VERIFIED, RunState, TaskView
from .marginal_action import MarginalAction


class OnlineCalibration(MarginalAction):
    name = "online_calibration"

    # Beta prior equivalent sample size. For coding, the prior mean is inherited
    # from MarginalAction and acts as a strong cold-start fallback.
    PRIOR_TRIALS = 12.0
    # Log-cost prior equivalent sample size; avoids overfitting rare cheap calls.
    COST_PRIOR_TRIALS = 5.0
    # Never infer the outcome of a text answer from "answered_unverified".
    MIN_OBSERVATIONS_FOR_COST = 1

    @staticmethod
    def _phase(task: TaskView, state: RunState) -> str:
        attempts = [a for a in state.attempts(task.task_id)
                    if a.kind not in ("vote", "diagnose")]
        if task.type == "coding":
            return "oneshot" if not attempts else "agent"
        return "oneshot" if len(attempts) < 2 else "agent"

    @staticmethod
    def _bucket(task: TaskView) -> str:
        if task.type != "coding":
            return "all"
        # A large file can require a very different generation budget.
        return "large" if task.files_bytes >= 5000 else "small"

    @staticmethod
    def _is_valid_cost_record(attempt) -> bool:
        # Only attempts that made actual, non-error requests are observations.
        if attempt.kind in ("vote", "diagnose") or attempt.cost <= 0:
            return False
        return bool(attempt.calls) and all(not c.error for c in attempt.calls)

    def _observations(self, task: TaskView, state: RunState):
        """Use only comparable *completed*, model-billed attempts.

        Task-level features are not present in AttemptResult, so size-specific
        pooling cannot safely be reconstructed from history. We therefore pool
        per category and attempt kind; task size still affects the baseline
        prior cost, not the learned observation buckets.
        """
        phase = self._phase(task, state)
        out = []
        for a in state.history:
            if a.kind != phase:
                continue
            # Task type is not stored in AttemptResult; infer it exclusively
            # from the task-id prefix when unambiguous. Avoid silently mixing
            # unrelated tasks or pretending to know labels for unknown ids.
            ty = self._type_from_id(a.task_id)
            if ty != task.type or not self._is_valid_cost_record(a):
                continue
            out.append(a)
        return out

    @staticmethod
    def _type_from_id(task_id: str) -> str | None:
        s = task_id.lower()
        for prefix, ty in (("data_analysis", "data_analysis"),
                           ("coding", "coding"), ("math", "math"),
                           ("search", "search")):
            if s == prefix or s.startswith(prefix + "_") or s.startswith(prefix + "-"):
                return ty
        return None

    def next_action(self, task: TaskView, state: RunState) -> tuple[float, float]:
        prior_p, prior_cost = super().next_action(task, state)
        obs = self._observations(task, state)
        if not obs:
            return prior_p, prior_cost

        # A cost is observable regardless of whether the answer is correct.
        # Smooth costs in log space to avoid one long generation dominating.
        log_prior = math.log(max(50.0, prior_cost))
        log_mean = (self.COST_PRIOR_TRIALS * log_prior +
                    sum(math.log(max(50.0, a.cost)) for a in obs)) / (
                        self.COST_PRIOR_TRIALS + len(obs))
        estimated_cost = max(50.0, math.exp(log_mean))

        if task.type != "coding":
            # Never treat answered_unverified / votes / LLM self-confidence
            # as correct labels for math, search or data_analysis.
            return prior_p, estimated_cost

        successes = sum(a.status == VERIFIED and a.verify == "unittest" for a in obs)
        failures = sum(a.status == FAILED for a in obs)
        n = successes + failures
        if n == 0:
            return prior_p, estimated_cost
        posterior_p = (self.PRIOR_TRIALS * prior_p + successes) / (
            self.PRIOR_TRIALS + n)
        return min(1.0, max(0.0, posterior_p)), estimated_cost
