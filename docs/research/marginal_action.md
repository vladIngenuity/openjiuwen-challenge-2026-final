# Experimental marginal-action scheduler

**Status: experiment only. Do not merge into the contest default without a
real-Qwen, full-Executor held-out comparison.** Branch is stacked on #27 to
inherit aggregate per-task budget enforcement.

## Research inspiration (not an implementation claim)

- AdaCompute, https://arxiv.org/abs/2604.14853 — use marginal utility
  and a compute budget rather than uniform allocation. The paper's actual
  oracle is over sampled response counts {1,2,4,8,16}; ours is a simpler,
  entirely heuristic next-attempt scheduler.
- CoBa, https://arxiv.org/abs/2608.07424 — compete for compute across
  generation, verification and stopping. This prototype **only** prioritizes
  pending attempts, and inherits Baseline's verification; it is NOT full CoBa.

## Difference from Baseline

Baseline prioritizes every first attempt before any second attempt via
`len(state.attempts(task_id))` in the ordering key. Here every pending task's
next action receives a score:

`score = task.reward * estimated_incremental_success / estimated_action_cost`

The prior P(success) comes from Baseline. Multiply it by 0.45 for every
previous unsuccessful attempt, or by 0.20 for an INFEASIBLE_CLAIMED attempt.
An additional attempt has estimated cost
`min(AGENT_CAP, max(50, 1.35 * first_cost))`.

These coefficients are **unverified priors**. They are not calibrated and
may be wrong. No training data or hidden answer is used. There are no
model changes, API calls in the Strategy, or new dependencies.

Select with `--strategy marginal_action` (check CLI help for exact syntax).
The default remains `baseline`.

## Required evaluation before enabling

1. Verify CI and Docker against PR #27 and the final image.
2. Hold out complete task families, not individual repeated generations.
3. Compare `baseline` and `marginal_action` on the **same** independent
   tasks, total 100000 contest units, same available models, same constraints.
4. Measure correct reward (private grader), total and per-category token
   cost, false infeasible, failures, remaining budget, elapsed time.
5. Compare means and bootstrap intervals across task families. Abort if no
   reliable improvement or if expensive coding tasks regress.
6. Ablate RETRY_MULTIPLIER and CLAIM_MULTIPLIER; do not tune on the held-out set.
