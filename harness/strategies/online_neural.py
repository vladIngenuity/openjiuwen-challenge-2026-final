"""Online MLP scheduler; only the scheduler's weights are trained, never Qwen.

A tiny 10 -> 12 -> 2 neural network (pure Python) predicts:
  head 0: log(observed action cost / Baseline prior cost)
  head 1: log-odds correction to Baseline predicted Coding success

The network starts at zero corrections and is updated *after completed actions*
by Executor's explicit observe hook. We never learn correctness from
answered_unverified, votes, self-confidence, or LLM infeasibility claims.
Classification targets are publicly-test-verified Coding successes or fully
charged Coding failures; these are noisy surrogates for private grader reward.

Uses no disk storage and no ML framework; weight updates cost 120 multiplies
per action, negligible relative to Qwen requests. Not enabled by default.
"""
from __future__ import annotations

import math

from ..strategy import FAILED, VERIFIED, PENDING, TaskView, RunState
from .baseline import Baseline


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-min(x, 50.0)))
    z = math.exp(max(x, -50.0))
    return z / (1.0 + z)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class TinyMLP:
    """One hidden layer, SGD with small L2 regularization, reproducible init."""

    INPUTS = 10
    HIDDEN = 12
    LR_COST = 0.012
    LR_PROB = 0.006

    def __init__(self):
        self.w1 = [[0.09 * math.sin((h+1)*13 + (i+1)*7)
                    for i in range(self.INPUTS)]
                   for h in range(self.HIDDEN)]
        self.b1 = [0.12] * self.HIDDEN
        self.w2 = [[0.0] * self.HIDDEN for _ in range(2)]
        self.b2 = [0.0, 0.0]
        self.cost_samples = 0
        self.label_samples = 0

    def forward(self, x):
        h = [max(0.0, b + sum(wi*xi for wi,xi in zip(row,x)))
             for b,row in zip(self.b1,self.w1)]
        y = [b + sum(wi*hi for wi,hi in zip(row,h))
             for b,row in zip(self.b2,self.w2)]
        return h,y

    def update(self, x, *, cost_target=None, label=None, p0=None):
        h,y = self.forward(x)
        errors = [0.0, 0.0]
        if cost_target is not None and math.isfinite(cost_target):
            errors[0] = _clip(y[0] - _clip(cost_target, -2.5, 2.5), -2, 2)
            self.cost_samples += 1
        if label is not None and p0 is not None:
            base_logit = math.log(p0/(1-p0))
            p = _sigmoid(base_logit + y[1])
            errors[1] = _clip(p - label, -1, 1)
            self.label_samples += 1
        old_w2 = [row[:] for row in self.w2]
        rates = (self.LR_COST, self.LR_PROB)
        for o in range(2):
            if (o==0 and cost_target is None) or (o==1 and label is None):
                continue
            err, lr = errors[o], rates[o]
            for j in range(self.HIDDEN):
                self.w2[o][j] -= lr*(err*h[j] + 0.0001*self.w2[o][j])
            self.b2[o] -= lr*err
        for j in range(self.HIDDEN):
            if h[j] <= 0:
                continue
            grad = sum(errors[o]*old_w2[o][j]*rates[o]
                       for o in range(2))
            for i in range(self.INPUTS):
                self.w1[j][i] -= grad*x[i]
            self.b1[j] -= grad


class OnlineNeural(Baseline):
    """Baseline fallback at cold-start; neural cost/accuracy after feedback."""

    name = "online_mlp"

    def __init__(self):
        self.model = TinyMLP()

    @staticmethod
    def _features(t: TaskView, attempt: int) -> list[float]:
        types = ("math", "search", "data_analysis", "coding")
        return [float(t.type == ty) for ty in types] + [
            _clip((attempt-1)/2, 0, 1),
            _clip(math.log1p(max(0,t.instruction_chars))/9, 0, 1),
            _clip(math.log1p(max(0,t.files_bytes))/12, 0, 1),
            _clip(math.log1p(max(0,t.n_files))/5, 0, 1),
            float(t.det_status == "partial"),
            float(t.det_status == "maybe_infeasible"),
        ]

    def _prior_cost(self, t, state):
        # Do not train on a moving online type_stats baseline: it creates
        # a target distribution that changes as earlier calls complete.
        s = RunState(state.budget_total, state.spent, state.remaining,
                     state.elapsed, state.time_left)
        return Baseline.cost(self, t, s)

    def _prior_p(self, t, state):
        s = RunState(state.budget_total, state.spent, state.remaining,
                     state.elapsed, state.time_left)
        return _clip(Baseline.p_success(self, t, s), 0.05, 0.95)

    def _predict(self, t, state, attempt):
        x = self._features(t, attempt)
        _, y = self.model.forward(x)
        # Trust the network gradually after seeing enough real observations.
        cost_conf = min(1.0, self.model.cost_samples/12.0)
        prob_conf = min(1.0, self.model.label_samples/20.0)
        predicted_cost = self._prior_cost(t,state)*math.exp(
            _clip(cost_conf*y[0], -1.2, 1.2))
        p0 = self._prior_p(t,state)
        p = _sigmoid(math.log(p0/(1-p0)) +
                     _clip(prob_conf*y[1], -1.0, 1.0))
        return _clip(p,0.01,0.99), max(50.0,predicted_cost)

    def order(self, tasks: list[TaskView], state: RunState) -> list[str]:
        scored=[]
        for t in tasks:
            if state.status_by_task.get(t.task_id,PENDING) != PENDING:
                continue
            attempt = 1 + len([a for a in state.attempts(t.task_id)
                               if a.kind not in ("vote","diagnose")])
            p,c = self._predict(t,state,attempt)
            # Preserve Baseline's first-try-before-retry safety.
            # Only the learned score changes within the same attempt count.
            scored.append((self._llm_infeasible_claims(t,state),
                           attempt, -(t.reward*p/c),t.task_id))
        scored.sort()
        return [t[-1] for t in scored]

    def observe(self, task: TaskView, result, state: RunState):
        """Online SGD immediately after Executor completed the attempt.

        Called only once per non-vote attempt; it is not invoked for skipped
        or unbilled actions and never sees reference answers.
        """
        if result.kind not in ("oneshot","agent") or result.cost <= 0:
            return
        if not result.calls or any(c.error for c in result.calls):
            return
        x = self._features(task, result.attempt)
        prior = max(50.0,self._prior_cost(task,state))
        target = math.log(max(1.0,result.cost)/prior)
        label=None
        if task.type == "coding":
            if result.status == VERIFIED and result.verify == "unittest":
                label=1.0
            elif result.status == FAILED:
                # A charged unsuccessful coding attempt is an action failure.
                # Not a claim about the true difficulty of this task.
                label=0.0
        self.model.update(x, cost_target=target, label=label,
                          p0=self._prior_p(task,state) if label is not None else None)
