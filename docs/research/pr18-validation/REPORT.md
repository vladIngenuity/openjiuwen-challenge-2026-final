# PR18: independent private validation on batch-022

Date: 12 November 2026. This completes the requested local private assessment from [issue 15](https://github.com/ArciomKapitonau/openjiuwen-harness/issues/15#issuecomment-6808356000). PR18 remains unmerged; main, the Collector and batch-023 were not changed or opened.

**The time improvement reproduces; six public passes mean only one hidden-test pass.** This is a deterministic-only, zero-model experiment. It does not measure the accuracy of the full Qwen-enabled agent.

## Frozen inputs and protocol

- Readiness base: `d90b7979cfdf707ceba387e12417527e35253991`.
- Exact reviewed PR18 head: `f4d8b2fec90139998bdaffdc5e66ee4288e3d4e1`, including PR17's bytes/probe fix. Seven changed files were fetched from the private repository and individually Git-blob-hash verified against the API; the baseline was copied from the owning local Git commit.
- Authorized public corpus: 100 tasks, 25 per type; 213 files validated against the public inventory. ZIP SHA-256: `b56eed45a35eb7a33661bf1eb51e7922e7bdeb77ad31eb2c7a6b801488b65e40`.
- All solver runs use fresh public-only copies, constructed empty environments, model access off, strict isolation and budget 100,000. The PR18 “default” row means its default 30/90-second limits; isolation was explicitly strict. The same host supports Landlock/seccomp.
- Solver runs completed before the independent grader opened the private archive. Expected answers, reference code and hidden source were not given to the scheduler, repair heuristics or any model. No private source or reference answer is included in this PR.
- The grader checks both public and hidden Coding suites, exact feasible text answers, false INFEASIBLE claims and skips. Per-task bits remain local in mode-0600 sidecars. Published data are aggregate only.
- Timings are single runs on a shared host, not repeated controlled latency estimates. They establish a large observed reduction, not a precise performance confidence interval.

## Measured results

| Version | Wall time | Publicly verified Coding | Hidden-correct Coding | Reward / feasible maximum | False internal verifications |
|---|---:|---:|---:|---:|---:|
| Readiness base | 134.64 s | 6 | 1 | 10 / 421 | 5 |
| PR18, task 30 s / phase 90 s | 44.21 s | 6 | 1 | 10 / 421 | 5 |
| PR18, task 12 s / phase 90 s | 24.82 s | 4 | 0 | 0 / 421 | 4 |
| Follow-up, task 30 s / phase 90 s | 45.21 s | 6 | 1 | 10 / 421 | 5 |

PR18 is about **3.05× faster** than the readiness base in this run, with the same hidden reward. The 12-second variant loses the sole hidden-correct repair; its lower elapsed time is not a quality win on this batch. The follow-up's run source digest is `e48f007aefaa16a2efd0f5aec5478eb0639513249f9084405d329d58156142b9`.

There are 80 feasible and 20 infeasible tasks. Math, Search and Data Analysis produce no feasible correct answers in these deterministic-only runs. All 20 infeasible tasks are skipped, with zero INFEASIBLE claims and zero false INFEASIBLE claims. Correctly recognizing an infeasible task earns zero contest reward. The 30-second variants leave 79 feasible tasks without a correct result; the 12-second variant leaves 80. The base logs 94 pending tasks without recording each in its trace; PR18/follow-up correctly finalize them as skipped.

The base bytes serialization exception reproduces in the solver log; PR18 avoids it. The fix deliberately skips unsupported differential probes rather than fabricating JSON values or changing test semantics.

## Check the checker

A grading regression could falsely make every candidate fail. Independent controls therefore ran in the private grader:

- **25/25 private reference implementations pass the public suites.**
- **25/25 private reference implementations pass the hidden suites.**
- **0/25 original broken public implementations pass the hidden suites.**

Reference sources existed only in temporary grading workspaces and were removed. No reference was used to choose a repair or tune a task-specific rule. No repair algorithm was changed based on hidden labels; follow-up changes concern isolation, output verification, dependencies and formatting compatibility.

## Confirmed issues and follow-up

1. **Forged stdout:** PR18 accepted a module that printed a `Ran 1 tests ...` line and immediately called `_exit(0)`. The follow-up requires a structured completion record tied to the current invocation and rejects this early-exit spoof. It also rejects basic monkeypatching of unittest assertions.
2. **Sibling resource limits:** PR18 let workspace Python change the open-file limit of a disposable sibling process using `prlimit`. The follow-up's argument-filtered seccomp rule blocks non-self targets while retaining self limit access. The test creates, checks and removes only its own sibling process.
3. **Isolation downgrade:** Restore `strict` as default. Explicit `auto` now probes a trusted no-op before running submitted code. A task's error text and exit code cannot trigger a retry without isolation.
4. **Installed libraries:** In the local pinned Python 3.12 environment, original PR18 cannot import numpy/pandas in the restricted `-S` child; the follow-up can, still under Landlock/seccomp. Explicit purelib/platlib roots are added through a trusted bootstrap; `site` and `.pth` hooks are not executed.
5. **Integer formatting:** Accept quoted integers and integral decimal forms such as `42.0` with exact arithmetic; reject non-integral/NaN/Inf/malformed input. Exact-string values keep punctuation.
6. **Coding marker:** Write `DONE` at task root after verification for compatibility. The grader ignores the marker as evidence and executes the code.
7. **Unknown usage:** Retain conservative settlement/stop behavior. There is no verified provider cost bound supporting a safe relaxation; the task did not call a real proxy.

**The forged-verdict P1 is not fully closed.** A synthetic follow-up probe confirms that arbitrary submitted Python can inspect the runner's frames and forge a completion record from the same interpreter. A nonce is not a process trust boundary. Full adversarial grading needs trusted assertions and submitted code in different processes with typed, bounded RPC; this requires support for functions, objects, iterators, exceptions and mutation semantics. The current finite-suite comparison concerns the authored modules and deterministic mutations, not a claim of secure evaluation of hostile submissions.

## Verification

- Original PR18: **47 tests pass**.
- Follow-up: **59 tests pass on Python 3.14** and **59 on Python 3.12**. Synthetic tests verify private/public channel separation and non-export of reference values.
- Existing pinned **openJiuwen 0.1.19**: offline API construction/self-check and **8/8 bundled public samples pass**, no model invocation. A dummy localhost client is constructed; actual credentials are absent.
- Real numpy/pandas import under strict isolation succeeds in the installed local Python 3.12 environment; the equivalent original PR18 check fails.
- `git diff --check` passes. Offline CI for Python 3.12/3.14 is included; see the PR's check status separately.
- Real Qwen, provider quota/accounting, Docker image execution and Windows are **not tested**. No API-key read or real-model request was performed. Collector sources, checkpoints and processes were left unchanged.

See [aggregate-report.json](aggregate-report.json), [reproduction](REPRODUCE.md) and [integration decisions](INTEGRATION.md). The branch is a reviewable follow-up to PR18; it does not merge PR18 or PR19, and does not authorize a paid run.
