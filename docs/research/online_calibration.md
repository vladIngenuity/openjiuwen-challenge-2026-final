# Online calibration strategy (experimental, opt-in)

**No Qwen parameter training. No extra token spend. Not enabled by default.**

This module extends the `marginal_action` strategy with online Bayesian
shrinkage. It watches completed attempts in the Executor's existing
`RunState.history`, updates estimated costs from valid charged attempts, and
updates estimated probability of correctness **only for Coding tasks with
verified test outcomes**. For Math, Search and Data Analysis, an output is
`answered_unverified`, so its correctness is *unknown* and is not used as
a positive label. Votes / model confidence are not truth.

No files are read or written, no side effects in Strategy methods, no new
dependencies or additional LLM calls. All costs are contest units.

## Online update

First get the prior (from MarginalAction):
`p0, c0 = super().next_action(task, state)`.

Group previously completed attempts by category and action kind, using
unambiguous task-id prefixes; nonstandard IDs cannot be pooled without
extending AttemptResult to include task.type. Invalid or uncharged requests
and vote/diagnostic results are excluded.

With n verifiable Coding observations, of which k are tested successes:
`p = (12*p0 + k)/(12+n)`.
This is a Beta-binomial shrinkage posterior conditional on the assumed prior.
A coding success is `VERIFIED` and `verify == 'unittest'`. Failed coding
attempts with valid billed calls count as observed failures. This measures
success under **public tests**, not hidden final correctness.

With m valid cost observations:
`log(c) = (5*log(c0) + sum(log(max(50, charged_cost))))/(5+m)`.
This is log-cost shrinkage, not a full likelihood-based uncertainty model.
Training updates occur automatically after each attempt through RunState;
the model does not need to be serialized.

Run: `--strategy online_calibration` (verify supported CLI syntax).
Default `baseline` remains unchanged. The PR is stacked on #28 and #27,
and is **not merge-ready** without integration and real-Qwen validation.

## Research limitations and next steps

1. **Critical:** task types are absent from AttemptResult. We infer the
   category only for standard task_id prefixes. Real competition IDs must
   follow that convention. Otherwise no online learning occurs.
2. Public coding test success is a weak surrogate; keep strong shrinkage.
3. There is selection bias: the Strategy observes only actions it chooses;
   estimates can be biased without controlled exploration or an
   independently collected validation set.
4. This is not fitted on the Collector 415x50 corpus because the current
   connector review has not established the raw dataset schema/labels.
   Import should be implemented only after verifying those files.
5. Retain a disabled fallback. Validate as full Executor episodes under
   100k contest units and equal time with held-out task families, not
   single-request replay.
6. Measure reward and regressions across four categories, token cost,
   false infeasible, and failures. Never use final hidden ground truth
   for online training.
