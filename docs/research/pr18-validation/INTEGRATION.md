# Review decisions and integration with PR19

PR18 includes PR17's non-JSON differential-probe fix. Its 47 original tests pass locally. Its default deterministic limits improve elapsed time on this public batch without a measured loss of hidden-test reward, but public verification is a weak correctness proxy. No per-task template or algorithm repair was tuned using the private grading results.

| Review question | Follow-up decision |
|---|---|
| Missing/inconsistent provider usage stops the run | Keep conservative settlement and stop. The provider's true cost is unknown; relaxing this without a verified upper-bound contract could violate budget safety. No real proxy was accessed. |
| Integer `42.0` and wrapping quotes | Accept only syntactically integral decimal forms and matched quotes for integer checks, using arbitrary-precision integer parsing. Reject fractions, malformed grouping, NaN/Inf and unbounded exponent syntax. Exact strings keep their punctuation and quotes. |
| Coding `answer.txt` | Write a compatibility `DONE` marker at task root only after public code verification. Grading still executes the actual code; the marker alone earns nothing. Do not duplicate it into workspace. |
| Python `-S` disables installed numpy/pandas | Keep startup isolation and add explicit interpreter-owned library roots through a trusted bootstrap, without `site` or `.pth` execution. Verify actual numpy/pandas import in the installed local environment. |
| `prlimit` can affect siblings | Restrict `prlimit64` to pid 0 (self) in seccomp. Verify denial against a disposable sibling process, with its limits unchanged. |
| Test verdict can be forged | Reject console-only verdicts/early exits, require a nonce-bound structured completion record and detect basic unittest monkeypatching. **Partial mitigation only:** arbitrary Python can inspect frames in the same interpreter. Full hostile-code grading remains unresolved. |
| Default automatic downgrade of isolation | Restore `strict` default. Explicit `auto` probes only trusted code before execution; a submitted program cannot trigger downgrade by printing an error and exiting 125. |

The argument-filter definitions follow the [libseccomp header](https://github.com/seccomp/libseccomp/blob/main/include/seccomp.h.in); pid 0 semantics follow [Python resource documentation](https://docs.python.org/3/library/resource.html#resource.prlimit). The regression changes only a disposable process created by the test, never a Collector or other user process.

PR19 (`vlad/agent-strategy-laboratory`) and PR18 have overlapping foundations. The follow-up does not merge or rewrite either branch. Both retain Strategy contract 1.0; compatibility at the method/field level is checked by the existing suite. This does not establish that the concurrent Executor gains match offline single-request replay.

Before combining PR19 with this follow-up, manually reconcile `harness/sandbox.py`, `_isolated.py`, `_test_runner.py`, `pipeline.py`, `llm_solvers.py`, and the ledger/transport/Executor changes. Preserve the library bootstrap and completion protocol as a unit; port PR17's probe handling and PR18's time/weak-fix logic together. Keep exact-tenths ledger tickets and stop/cancellation accounting from PR19 while retaining PR18's provider-code handling. Rerun both test suites, public samples, budget mocks and profile-specific validation. Do not treat the two draft branches as an automatic merge approval.

For fully hostile submissions, a stronger design keeps trusted test assertions in a separate process from the submitted module and exchanges only typed, bounded call arguments/results. Functions, stateful objects, iterators, exceptions and mutation semantics need explicit support; until that boundary exists, mark hostile-code grading unsupported. A nonce in the submitted interpreter is not cryptographic isolation.
