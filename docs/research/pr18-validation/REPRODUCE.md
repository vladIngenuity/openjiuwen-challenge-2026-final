# Reproduce the PR18 validation

The task is to validate PR18 (`f4d8b2fec90139998bdaffdc5e66ee4288e3d4e1`) against its readiness base (`d90b7979cfdf707ceba387e12417527e35253991`) on the authorized **batch-022** only. The final batch-023 is excluded. Original inputs, Collector sources/checkpoints/processes and main branches are not modified.

## Public execution

Use separate frozen source checkouts for the two commits and the follow-up. Run in a fresh output directory for each variant; `run_public` does not accept private inputs. The public ZIP must exactly match its supplied file inventory and must not contain private task metadata. Model-related environment values are absent from the child process; only explicitly constructed variables are passed. Execution requires strict Linux isolation.

```bash
env -i PATH="$PATH" PYTHONPATH=. HARNESS_ISOLATION=strict \
  python -m tools.validation.run_public \
  --source /approved/frozen/source \
  --public /approved/public/batch-022.zip \
  --inventory /approved/public/batch-022.inventory.json \
  --out /tmp/pr18-review/public-run --task-seconds 30 --phase-seconds 90
```

Repeat with the readiness source, PR18 source, and follow-up source. The base ignores the new deterministic time-limit variables, as it predates them. An additional PR18 variant uses `--task-seconds 12`. The runner records wall time, charged units, model calls, status counts, public archive digest and source-code digest. It never opens a private archive. Archive paths, symlinks, duplicate entries and inventory checks are validated before execution.

## Independent private evaluation

Finish solver runs first. The following is a separate grading process. Hidden source is sent through a closed-before-import grader channel; no model client is imported, no reference files are placed into the solver workspace, and no source or expected answer is exported. The grader still executes submitted Python in the test interpreter; see the explicit adversarial limitation in REPORT.md.

```bash
env -i PATH="$PATH" PYTHONPATH=. HARNESS_ISOLATION=strict \
  python -m tools.validation.grade_archive \
  --tasks /tmp/pr18-review/public-run/tasks \
  --trace /tmp/pr18-review/public-run/trace.json \
  --private /approved/private/batch-022.private.zip \
  --out /tmp/pr18-review/grading

env -i PATH="$PATH" PYTHONPATH=. HARNESS_ISOLATION=strict \
  python -m tools.validation.controls \
  --public /approved/public/batch-022.zip \
  --private /approved/private/batch-022.private.zip \
  --out /tmp/pr18-review/controls.json
```

Only aggregate metrics are published. Per-task grading bits are stored in a mode-0600 local file outside Git. Actual private inputs and solver outputs are not uploaded. Feasible text uses exact comparison; Coding must pass both public and hidden suites. Hidden-suite failures never become repair feedback. Infeasible recognition yields zero contest reward; false INFEASIBLE claims, skipped infeasible tasks and unresolved feasible tasks are reported separately.

The controls execute private reference solutions only inside the grader, never the solver: reference public/hidden passes are positive controls; original broken public modules are negative controls. Private files are not extracted into persistent directories.

## Tests and optional libraries

```bash
env -i PATH="$PATH" PYTHONPATH=. HARNESS_ISOLATION=strict \
  python -m unittest discover -s tests -v

env -i PATH="$PATH" PYTHONPATH=. HARNESS_ISOLATION=strict \
  HARNESS_TRACE=/tmp/pr18-review/selfcheck-trace.json \
  python tools/selfcheck.py
```

The full self-check needs the pinned openJiuwen environment. It constructs a dummy localhost client but never invokes a model. All public samples run with model access disabled. The ordinary unittest suite uses synthetic fixtures and a loopback mock.

The library bootstrap keeps `-I -S -B` and adds only the parent interpreter's explicit `sysconfig` purelib/platlib directories to the restricted child. It does not execute `site`, `.pth` files or workspace startup hooks. A separate local Python 3.12 environment with numpy/pandas was used to test installed-library imports under Landlock/seccomp. Docker and Windows were not tested.

The follow-up restores `strict` as the default. `auto` remains an explicit trusted-input compatibility mode; its decision to degrade isolation now uses a trusted preflight rather than the submitted task's output. Private grading rejects non-strict mode.
