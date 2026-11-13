# Справочник функций исходного кода

Сгенерировано по AST текущего checkout. Охват: `run_agent.py`, `harness/**/*.py`,
`tools/**/*.py` (включая функции командных инструментов и вложенные функции).
Сигнатуры и строки исходника точные; описание берётся из первой строки docstring.
Отсутствующий docstring указан явно, чтобы не выдавать догадку за контракт.
Внешние зависимости, тесты, сгенерированные корпуса и старые резервные копии
в справочник не входят. Ссылка на строку ведёт к определению в GitHub.
Всего определений: **336**.

## `run_agent.py`

- [`_prepare_runtime()`](../../run_agent.py#L26) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../run_agent.py#L46) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main.terminate(signum, frame)`](../../run_agent.py#L69) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/_isolated.py`

- [`checked(value)`](../../harness/_isolated.py#L23) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`restrict_files(writable, helper)`](../../harness/_isolated.py#L30) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`restrict_files.allow(path, rights)`](../../harness/_isolated.py#L42) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`restrict_syscalls(seccomp)`](../../harness/_isolated.py#L78) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../harness/_isolated.py#L127) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/_python_runner.py`

- [`main()`](../../harness/_python_runner.py#L9) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/_test_runner.py`

- [`main()`](../../harness/_test_runner.py#L18) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main.intact()`](../../harness/_test_runner.py#L35) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/budget.py`

- [`cost_of(input_tokens: int, output_tokens: int, reasoning_tokens: int=0, *, reasoning_in_output: bool=True) -> float`](../../harness/budget.py#L16) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`estimate_tokens(text: str) -> int`](../../harness/budget.py#L22) — Conservative heuristic, NOT a formal upper bound on provider tokenization.
- [`BudgetLedger.__init__(self, total: float | None=None, reserve_frac: float=0.02)`](../../harness/budget.py#L37) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`BudgetLedger.remaining(self) -> float`](../../harness/budget.py#L58) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`BudgetLedger.usable(self) -> float`](../../harness/budget.py#L62) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`BudgetLedger.try_reserve(self, amount: float) -> Ticket | None`](../../harness/budget.py#L66) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`BudgetLedger._take_ticket(self, ticket: Ticket) -> float`](../../harness/budget.py#L77) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`BudgetLedger.commit(self, ticket: Ticket, input_tokens: int, output_tokens: int, reasoning_tokens: int=0, meta: dict | None=None) -> float`](../../harness/budget.py#L86) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`BudgetLedger.commit_uncertain(self, ticket: Ticket, meta: dict | None=None) -> float`](../../harness/budget.py#L110) — Charge full reservation and stop. No retry after unknown outcome.
- [`BudgetLedger.release(self, ticket: Ticket)`](../../harness/budget.py#L127) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`BudgetLedger.mark_dead(self, reason: str='unavailable')`](../../harness/budget.py#L131) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/executor.py`

- [`StrategyExecutor.__init__(self, harness, strategy, workers: int=5)`](../../harness/executor.py#L34) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`StrategyExecutor.view(self, t) -> TaskView`](../../harness/executor.py#L48) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`StrategyExecutor.state(self) -> RunState`](../../harness/executor.py#L66) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`StrategyExecutor._eligible(self, task_id: str) -> bool`](../../harness/executor.py#L78) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`StrategyExecutor._defer(self, task_id: str, why: str) -> None`](../../harness/executor.py#L82) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`StrategyExecutor._elapsed() -> float`](../../harness/executor.py#L87) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`StrategyExecutor._calls_since(self, n0: int, task_id: str) -> tuple[Call, ...]`](../../harness/executor.py#L91) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async StrategyExecutor._attempt(self, t, view: TaskView, attempt: int, model: str, cap: float, *, rescue: bool=False) -> AttemptResult`](../../harness/executor.py#L106) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`StrategyExecutor._task_left(t) -> float`](../../harness/executor.py#L188) — Remaining aggregate task budget across attempts, votes and diagnosis.
- [`async StrategyExecutor._vote(self, t, view: TaskView, first: AttemptResult, *, cap: float | None=None) -> AttemptResult | None`](../../harness/executor.py#L197) — Independent second opinion; change the answer only on a 2-of-3 majority.
- [`async StrategyExecutor._run_endgame(self) -> None`](../../harness/executor.py#L241) — Spend surplus on ranked verification only after the first pass.
- [`async StrategyExecutor._rescue_truncated(self, reserve: float, min_time: float) -> None`](../../harness/executor.py#L308) — Retry measured, truncated outputs once while surplus remains.
- [`async StrategyExecutor._diagnose(self, t, view: TaskView) -> None`](../../harness/executor.py#L370) — Short LLM feasibility/cost check, charged with tag plan:<id>.
- [`async StrategyExecutor._process(self, t) -> None`](../../harness/executor.py#L394) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`StrategyExecutor._stop(self) -> bool`](../../harness/executor.py#L451) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async StrategyExecutor._worker(self, wid: int) -> None`](../../harness/executor.py#L454) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async StrategyExecutor.run(self) -> None`](../../harness/executor.py#L479) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/llm.py`

- [`Usage.__new__(cls, input_tokens, output_tokens, reasoning_tokens, finish_reason='')`](../../harness/llm.py#L30) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`cap_scope(cap: float)`](../../harness/llm.py#L56) — Limit the total cost of LLM calls made inside this block to ``cap`` units.
- [`RateLimiter.__init__(self, rpm: int=30)`](../../harness/llm.py#L75) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async RateLimiter.acquire(self, time_left)`](../../harness/llm.py#L82) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`RateLimiter.complete(self)`](../../harness/llm.py#L91) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`ProxyError.__init__(self, status: int, body: str, headers=None)`](../../harness/llm.py#L102) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`classify_error(e) -> str`](../../harness/llm.py#L123) — quota: shared budget exhausted -> stop everything
- [`_http_status(e) -> int | None`](../../harness/llm.py#L147) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`LLM.__init__(self, ledger: BudgetLedger, max_concurrency: int | None=None, *, time_left=None)`](../../harness/llm.py#L164) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`LLM._oj_model(self, name: str)`](../../harness/llm.py#L192) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async LLM._call_oj(self, model: str, messages, max_tokens, tools)`](../../harness/llm.py#L209) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async LLM._call_raw(self, model, messages, max_tokens, tools)`](../../harness/llm.py#L231) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`LLM._post_urllib(self, body: dict) -> dict`](../../harness/llm.py#L262) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`LLM._fallback_model(self, model: str) -> str | None`](../../harness/llm.py#L275) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async LLM.chat(self, messages: list[dict], *, model: str=MODEL_FAST, max_tokens: int=400, tools: list[dict] | None=None, tag: str='') -> dict`](../../harness/llm.py#L282) — Return one answer and the total cost of its transport attempts.
- [`LLM._scopes(scope)`](../../harness/llm.py#L315) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`LLM._journal(self, event, meta)`](../../harness/llm.py#L320) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`LLM._commit(self, scope, ticket, usage, meta)`](../../harness/llm.py#L331) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`LLM._commit_uncertain(self, scope, ticket, meta)`](../../harness/llm.py#L339) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async LLM._request(self, transport, messages, model, requested, tools, tag, estimated_input)`](../../harness/llm.py#L347) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/llm_solvers.py`

- [`clean_instruction(ins: str) -> str`](../../harness/llm_solvers.py#L20) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`extract_code(text: str) -> str | None`](../../harness/llm_solvers.py#L26) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`normalize(ans: str, check: str) -> str | None`](../../harness/llm_solvers.py#L35) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`is_infeasible(text: str) -> bool`](../../harness/llm_solvers.py#L53) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async _code_answer(llm: LLM, task, user: str, cwd: Path, model: str, max_tokens: int, tag: str, repairs: int=0)`](../../harness/llm_solvers.py#L64) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_det_hint(task) -> str`](../../harness/llm_solvers.py#L101) — A maybe_infeasible signal from the deterministic phase (e.g. a declared
- [`async solve_math(llm: LLM, task, model=MODEL_FAST, repairs: int=0, max_tokens: int=350)`](../../harness/llm_solvers.py#L113) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async solve_data(llm: LLM, task, model=MODEL_FAST, repairs: int=0, max_tokens: int=450)`](../../harness/llm_solvers.py#L123) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async solve_search(llm: LLM, task, model=MODEL_FAST)`](../../harness/llm_solvers.py#L145) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async solve_coding(llm: LLM, task, model=MODEL_FAST, attempts: int=2, start_files: dict | None=None, min_output_tokens: int=0)`](../../harness/llm_solvers.py#L171) — One-shot whole-file repair with test feedback.
- [`_inside(p: Path, root: Path) -> bool`](../../harness/llm_solvers.py#L233) — True if p (after resolving symlinks and ..) lies within root.
- [`check_shell(command: str) -> str | None`](../../harness/llm_solvers.py#L246) — Reject anything but read-only inspection pipelines inside the workspace.
- [`_make_tools(cwd: Path, state: dict)`](../../harness/llm_solvers.py#L265) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_make_tools.list_files(path: str='.') -> str`](../../harness/llm_solvers.py#L266) — List files under a directory (relative).
- [`_make_tools.read_file(path: str, max_chars: int=4000) -> str`](../../harness/llm_solvers.py#L274) — Read a text file (relative path).
- [`_make_tools.write_file(path: str, content: str) -> str`](../../harness/llm_solvers.py#L281) — Overwrite a text file (relative path).
- [`_make_tools.run_python(code: str) -> str`](../../harness/llm_solvers.py#L291) — Run a Python 3 snippet in the directory and return stdout/stderr.
- [`_make_tools.run_shell(command: str) -> str`](../../harness/llm_solvers.py#L296) — Run a read-only shell command (ls, grep, cat, head, wc, python3 file.py ...).
- [`_make_tools.submit(answer: str) -> str`](../../harness/llm_solvers.py#L304) — Submit the final answer.
- [`_schemas(funcs: dict)`](../../harness/llm_solvers.py#L313) — Tool schemas; built through openJiuwen's @tool when available.
- [`async agent_solve(llm: LLM, task, cap: float, model=MODEL_FAST, max_steps: int=12, stop_repeated: bool=False)`](../../harness/llm_solvers.py#L345) — Generic tool-using agent with a hard per-task token cap. Context is kept

## `harness/log.py`

- [`log(msg: str) -> None`](../../harness/log.py#L7) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`elapsed() -> float`](../../harness/log.py#L12) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/ml_features_v2.py`

- [`_log(count: int) -> float`](../../harness/ml_features_v2.py#L34) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`extract(instruction: str, workspace: Mapping[str, str]) -> list[float]`](../../harness/ml_features_v2.py#L38) — Extract deterministic features from public task inputs.

## `harness/pipeline.py`

- [`_env_seconds(name: str, default: float) -> float`](../../harness/pipeline.py#L22) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`type_of(t: Task) -> str`](../../harness/pipeline.py#L41) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.__init__(self, tasks_dir: Path, out_path: str | None, strategy: str='baseline')`](../../harness/pipeline.py#L55) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness._calls_for(self, t: Task) -> list[dict]`](../../harness/pipeline.py#L68) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.record(self, t: Task)`](../../harness/pipeline.py#L73) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.accept_answer(self, t: Task, answer: str, solver: str, note: str='', verify: str='none')`](../../harness/pipeline.py#L76) — verify: unittest (tests pass) \| det_parse \| vote \| none.
- [`Harness.record_code(self, t: Task, solver: str, note: str) -> None`](../../harness/pipeline.py#L86) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.accept_code(self, t: Task, files: dict, solver: str, note: str='') -> bool`](../../harness/pipeline.py#L92) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.mark(self, t: Task, status: str, note: str)`](../../harness/pipeline.py#L132) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.deterministic(self, t: Task)`](../../harness/pipeline.py#L138) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.apply_weak_fix(self, t: Task) -> bool`](../../harness/pipeline.py#L176) — Fallback for a coding task the model did not solve: publish the
- [`Harness.phase_deterministic(self)`](../../harness/pipeline.py#L184) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.p_success(self, t: Task) -> float`](../../harness/pipeline.py#L219) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.est_cost(self, t: Task) -> float`](../../harness/pipeline.py#L232) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async Harness.attempt_cheap(self, t: Task)`](../../harness/pipeline.py#L246) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness._consume(self, t: Task, r, solver: str) -> str`](../../harness/pipeline.py#L279) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.task_cap(self, t: Task) -> float`](../../harness/pipeline.py#L300) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.time_left(self) -> float`](../../harness/pipeline.py#L305) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async Harness.run_queue(self, tasks, fn, label)`](../../harness/pipeline.py#L308) — Run `fn` over tasks in order with up to 5 in flight.
- [`async Harness.run_queue.one(t)`](../../harness/pipeline.py#L312) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async Harness.phase_llm(self)`](../../harness/pipeline.py#L324) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async Harness.phase_llm.cheap(t)`](../../harness/pipeline.py#L330) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async Harness.phase_llm.escalate(t)`](../../harness/pipeline.py#L347) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async Harness.phase_verify(self)`](../../harness/pipeline.py#L376) — Second opinion on LLM-derived non-code answers while budget is ample.
- [`async Harness.run(self)`](../../harness/pipeline.py#L404) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Harness.summary(self)`](../../harness/pipeline.py#L426) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/preflight.py`

- [`parse_ratings(content: str, count: int) -> list[int] | None`](../../harness/preflight.py#L24) — Accept only an exact compact JSON array of integer ratings 0..10.
- [`make_batch(tasks) -> tuple[list[dict], list[str]]`](../../harness/preflight.py#L46) — Small inexpensive metadata snapshot only; prompt doesn't expose truth.
- [`async preflight_all(executor, *, max_fraction: float=0.2, max_total: float=2000.0, batch_size: int=10) -> dict[str, dict]`](../../harness/preflight.py#L61) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/sandbox.py`

- [`copy_inputs(src: Path, dst: Path, *, skip=SKIP, preserve_mode=False) -> None`](../../harness/sandbox.py#L28) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`scratch_copy(ws: Path) -> Path`](../../harness/sandbox.py#L47) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`isolation_mode() -> str`](../../harness/sandbox.py#L71) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_prefer_oom_kill()`](../../harness/sandbox.py#L75) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_limits(cpu: int)`](../../harness/sandbox.py#L86) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_limits.apply()`](../../harness/sandbox.py#L87) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`run_command(command: list[str], cwd: Path, timeout: float, *, writable: bool=False, helper: Path | None=None, separate_stderr: bool=False, stdin_text: str | None=None) -> tuple[int, str]`](../../harness/sandbox.py#L100) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_run(command, cwd, timeout, isolated, writable, helper, separate_stderr, stdin_text)`](../../harness/sandbox.py#L123) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`run_python(code: str, cwd: Path, timeout: int=20) -> tuple[int, str]`](../../harness/sandbox.py#L182) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`run_shell(cmd: str, cwd: Path, timeout: int=30) -> tuple[int, str]`](../../harness/sandbox.py#L194) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`run_suite(cwd: Path, test_file: Path | None, timeout: float=60, *, hidden_source: str | None=None) -> tuple[bool, str]`](../../harness/sandbox.py#L199) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/solvers/_mut_runner.py`

- [`_alarm(sig, frame)`](../../harness/solvers/_mut_runner.py#L35) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_set_alarm(_seconds)`](../../harness/solvers/_mut_runner.py#L43) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`load_module(name, src)`](../../harness/solvers/_mut_runner.py#L47) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`run_tests(test_src, test_file, tests)`](../../harness/solvers/_mut_runner.py#L56) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../harness/solvers/_mut_runner.py#L79) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/solvers/coding_solver.py`

- [`locate(instruction: str, ws: Path)`](../../harness/solvers/coding_solver.py#L41) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`locate.source(name)`](../../harness/solvers/coding_solver.py#L42) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`run_tests(ws: Path, test_file: Path, timeout: float=60)`](../../harness/solvers/coding_solver.py#L72) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`failing_tests(output: str) -> list[str]`](../../harness/solvers/coding_solver.py#L76) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_module_funcs(tree: ast.Module)`](../../harness/solvers/coding_solver.py#L82) — name -> (node, class_name\|None)
- [`_called_names(node) -> set[str]`](../../harness/solvers/coding_solver.py#L95) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`implicated(test_src: str, test_name: str, mod_tree: ast.Module) -> list[str]`](../../harness/solvers/coding_solver.py#L111) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`example_args(test_src: str, fname: str)`](../../harness/solvers/coding_solver.py#L145) — Literal argument tuples used with `fname` in the tests.
- [`_parents(root)`](../../harness/solvers/coding_solver.py#L162) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_replace(par, node, new)`](../../harness/solvers/coding_solver.py#L170) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for(node, local_names)`](../../harness/solvers/coding_solver.py#L186) — Yield (priority, description, fn(node, parents)) edits for one node.
- [`_edits_for.f(n, par, k=k, alt=alt)`](../../harness/solvers/coding_solver.py#L194) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, k=k)`](../../harness/solvers/coding_solver.py#L199) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L203) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, alt=alt)`](../../harness/solvers/coding_solver.py#L210) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L216) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f2(n, par)`](../../harness/solvers/coding_solver.py#L219) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L223) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L227) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L233) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, a=a)`](../../harness/solvers/coding_solver.py#L239) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, a=a)`](../../harness/solvers/coding_solver.py#L245) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, a=a)`](../../harness/solvers/coding_solver.py#L251) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, alt=alt)`](../../harness/solvers/coding_solver.py#L262) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L267) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L271) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f2(n, par)`](../../harness/solvers/coding_solver.py#L275) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f3(n, par)`](../../harness/solvers/coding_solver.py#L280) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f4(n, par)`](../../harness/solvers/coding_solver.py#L284) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, alt=alt)`](../../harness/solvers/coding_solver.py#L291) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, k=k)`](../../harness/solvers/coding_solver.py#L297) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L300) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, attr=attr, op=op)`](../../harness/solvers/coding_solver.py#L308) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, attr=attr)`](../../harness/solvers/coding_solver.py#L312) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L315) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L319) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L323) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, op=op)`](../../harness/solvers/coding_solver.py#L328) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, alt=alt)`](../../harness/solvers/coding_solver.py#L334) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par)`](../../harness/solvers/coding_solver.py#L338) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_edits_for.f(n, par, field=field, k=k)`](../../harness/solvers/coding_solver.py#L348) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`mutants(func_node)`](../../harness/solvers/coding_solver.py#L354) — Yield (priority, description, mutated_func_node).
- [`splice(src: str, func_node, new_func_node) -> str`](../../harness/solvers/coding_solver.py#L383) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_gen_like(v, rnd: random.Random)`](../../harness/solvers/coding_solver.py#L396) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`random_inputs(examples, n=48, seed=7, param_names=None)`](../../harness/solvers/coding_solver.py#L428) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_oracle_outs(short, inputs)`](../../harness/solvers/coding_solver.py#L488) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`choose_group(passing, sigs, prios, descs, short, inputs)`](../../harness/solvers/coding_solver.py#L501) — Pick the behaviour cluster most likely to be the true fix.
- [`choose_group.score(k)`](../../harness/solvers/coding_solver.py#L521) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_runner_call(payload: dict, cwd: Path, timeout: int=120)`](../../harness/solvers/coding_solver.py#L538) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`repair(instruction: str, ws: Path, max_seconds: float=120.0)`](../../harness/solvers/coding_solver.py#L556) — Returns dict(status=..., files={name: src}, note=...).
- [`repair.tests()`](../../harness/solvers/coding_solver.py#L566) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`repair.mutate(payload)`](../../harness/solvers/coding_solver.py#L569) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/solvers/data_solver.py`

- [`load_csv(path: Path)`](../../harness/solvers/data_solver.py#L12) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`find_csv(instruction: str, ws: Path) -> Path | None`](../../harness/solvers/data_solver.py#L18) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_num(v: str)`](../../harness/solvers/data_solver.py#L29) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_parse_filters(text: str, columns: list[str])`](../../harness/solvers/data_solver.py#L37) — Extract filters from the question tail. Returns (filters, leftover).
- [`_apply(rows, filters)`](../../harness/solvers/data_solver.py#L65) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`solve(instruction: str, ws: Path)`](../../harness/solvers/data_solver.py#L84) — ('answer', v, note) \| ('infeasible', None, note) \| None
- [`preview(path: Path, n: int=4) -> str`](../../harness/solvers/data_solver.py#L179) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/solvers/math_solver.py`

- [`_n(s: str) -> Fraction`](../../harness/solvers/math_solver.py#L22) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_split_sentences(text: str) -> list[str]`](../../harness/solvers/math_solver.py#L29) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_floor(x: Fraction) -> Fraction`](../../harness/solvers/math_solver.py#L37) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_round_mode(s: str) -> str | None`](../../harness/solvers/math_solver.py#L41) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_apply_round(x: Fraction, mode: str | None) -> Fraction | None`](../../harness/solvers/math_solver.py#L52) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_op(sentence: str, x: Fraction)`](../../harness/solvers/math_solver.py#L67) — Apply one sentence to the running value; return new value or None.
- [`solve(instruction: str)`](../../harness/solvers/math_solver.py#L147) — Return (answer_str, note) or None if not fully understood.

## `harness/solvers/search_solver.py`

- [`parse_kb(kb_dir: Path)`](../../harness/solvers/search_solver.py#L34) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_key_patterns(keys: set[str]) -> dict[str, list[str]]`](../../harness/solvers/search_solver.py#L62) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_find_entities(q: str, ents: dict)`](../../harness/solvers/search_solver.py#L73) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_unknown_names(q: str, ents: dict) -> list[str]`](../../harness/solvers/search_solver.py#L90) — Capitalised multi-word names in the question that are not in the KB.
- [`_answer_type(q: str) -> str | None`](../../harness/solvers/search_solver.py#L103) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_value_fits(val: str, atype: str | None, ents: dict) -> bool`](../../harness/solvers/search_solver.py#L116) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`solve(instruction: str, ws: Path)`](../../harness/solvers/search_solver.py#L128) — Return ('answer', value, note) \| ('infeasible', None, note) \| None.
- [`retrieve_context(instruction: str, ws: Path, limit_chars: int=3500) -> str`](../../harness/solvers/search_solver.py#L213) — Small relevant subset of the KB for the LLM fallback (one/two hops).
- [`retrieve_context.add(k)`](../../harness/solvers/search_solver.py#L224) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/__init__.py`

- [`get(name: str)`](../../harness/strategies/__init__.py#L35) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/ablations.py`

- [`OnlineCostOnly.next_action(self, task, state)`](../../harness/strategies/ablations.py#L28) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/baseline.py`

- [`_env_float(name: str, default: float) -> float`](../../harness/strategies/baseline.py#L27) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline.p_success(self, t: TaskView, state: RunState) -> float`](../../harness/strategies/baseline.py#L50) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline.cost(self, t: TaskView, state: RunState) -> float`](../../harness/strategies/baseline.py#L61) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline._llm_infeasible_claims(t: TaskView, state: RunState) -> int`](../../harness/strategies/baseline.py#L73) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline._claimed_limited(self, t: TaskView, state: RunState) -> bool`](../../harness/strategies/baseline.py#L76) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline._spent_on(t: TaskView, state: RunState) -> float`](../../harness/strategies/baseline.py#L80) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline.order(self, tasks: list[TaskView], state: RunState) -> list[str]`](../../harness/strategies/baseline.py#L84) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline.budget_for(self, task: TaskView, state: RunState) -> float`](../../harness/strategies/baseline.py#L91) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline.model_for(self, task: TaskView, state: RunState, attempt: int) -> str`](../../harness/strategies/baseline.py#L113) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline.should_escalate(self, task: TaskView, result: AttemptResult, state: RunState) -> bool`](../../harness/strategies/baseline.py#L124) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline.should_verify(self, task: TaskView, result: AttemptResult, state: RunState) -> bool`](../../harness/strategies/baseline.py#L137) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Baseline.should_diagnose(self, task: TaskView, state: RunState) -> bool`](../../harness/strategies/baseline.py#L143) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/empirical_hybrid.py`

- [`EmpiricalHybrid.p_success(self, task: TaskView, state: RunState) -> float`](../../harness/strategies/empirical_hybrid.py#L68) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`EmpiricalHybrid.cost(self, task: TaskView, state: RunState) -> float`](../../harness/strategies/empirical_hybrid.py#L71) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`EmpiricalHybrid.order(self, tasks: list[TaskView], state: RunState) -> list[str]`](../../harness/strategies/empirical_hybrid.py#L74) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`EmpiricalHybrid.budget_for(self, task: TaskView, state: RunState) -> float`](../../harness/strategies/empirical_hybrid.py#L89) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`EmpiricalHybrid.model_for(self, task: TaskView, state: RunState, attempt: int) -> str`](../../harness/strategies/empirical_hybrid.py#L94) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`EmpiricalHybrid.endgame_order(self, tasks: list[TaskView], state: RunState) -> list[str]`](../../harness/strategies/empirical_hybrid.py#L101) — Highest expected correction value per unit of verification first.

## `harness/strategies/fixed_models.py`

- [`AlwaysFast.model_for(self, task, state, attempt)`](../../harness/strategies/fixed_models.py#L12) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`AlwaysReason.model_for(self, task, state, attempt)`](../../harness/strategies/fixed_models.py#L18) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/marginal_action.py`

- [`MarginalAction.next_action(self, task: TaskView, state: RunState) -> tuple[float, float]`](../../harness/strategies/marginal_action.py#L28) — Estimated *incremental* success probability and next-action cost.
- [`MarginalAction.order(self, tasks: list[TaskView], state: RunState) -> list[str]`](../../harness/strategies/marginal_action.py#L44) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/online_calibration.py`

- [`OnlineCalibration._phase(task: TaskView, state: RunState) -> str`](../../harness/strategies/online_calibration.py#L31) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineCalibration._bucket(task: TaskView) -> str`](../../harness/strategies/online_calibration.py#L39) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineCalibration._is_valid_cost_record(attempt) -> bool`](../../harness/strategies/online_calibration.py#L46) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineCalibration._observations(self, task: TaskView, state: RunState)`](../../harness/strategies/online_calibration.py#L52) — Use only comparable *completed*, model-billed attempts.
- [`OnlineCalibration._type_from_id(task_id: str) -> str | None`](../../harness/strategies/online_calibration.py#L75) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineCalibration.next_action(self, task: TaskView, state: RunState) -> tuple[float, float]`](../../harness/strategies/online_calibration.py#L84) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/online_neural.py`

- [`_sigmoid(x: float) -> float`](../../harness/strategies/online_neural.py#L24) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_clip(x: float, lo: float, hi: float) -> float`](../../harness/strategies/online_neural.py#L31) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`TinyMLP.__init__(self)`](../../harness/strategies/online_neural.py#L43) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`TinyMLP.forward(self, x)`](../../harness/strategies/online_neural.py#L53) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`TinyMLP.update(self, x, *, cost_target=None, label=None, p0=None)`](../../harness/strategies/online_neural.py#L60) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineNeural.__init__(self)`](../../harness/strategies/online_neural.py#L95) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineNeural._features(t: TaskView, attempt: int) -> list[float]`](../../harness/strategies/online_neural.py#L99) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineNeural._prior_cost(self, t, state)`](../../harness/strategies/online_neural.py#L110) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineNeural._prior_p(self, t, state)`](../../harness/strategies/online_neural.py#L117) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineNeural._predict(self, t, state, attempt)`](../../harness/strategies/online_neural.py#L122) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineNeural.order(self, tasks: list[TaskView], state: RunState) -> list[str]`](../../harness/strategies/online_neural.py#L135) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`OnlineNeural.observe(self, task: TaskView, result, state: RunState)`](../../harness/strategies/online_neural.py#L150) — Online SGD immediately after Executor completed the attempt.

## `harness/strategies/qwen_preflight.py`

- [`QwenPreflight.order(self, tasks: list[TaskView], state: RunState) -> list[str]`](../../harness/strategies/qwen_preflight.py#L17) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`QwenPreflight.order.key(t)`](../../harness/strategies/qwen_preflight.py#L20) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/random_baseline.py`

- [`RandomBaseline._seed() -> str`](../../harness/strategies/random_baseline.py#L21) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`RandomBaseline.order(self, tasks: list[TaskView], state: RunState) -> list[str]`](../../harness/strategies/random_baseline.py#L24) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`RandomBaseline.order.key(t)`](../../harness/strategies/random_baseline.py#L28) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategies/reason_first_bounded.py`

- [`AlwaysReasonNoVote.should_verify(self, task, result, state)`](../../harness/strategies/reason_first_bounded.py#L13) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`ReasonFirstBounded.should_escalate(self, task, result, state)`](../../harness/strategies/reason_first_bounded.py#L23) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/strategy.py`

- [`RunState.attempts(self, task_id: str) -> list[AttemptResult]`](../../harness/strategy.py#L109) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`Strategy.order(self, tasks: list[TaskView], state: RunState) -> list[str]`](../../harness/strategy.py#L120) — Task ids to attempt next, best first. Called again after every
- [`Strategy.budget_for(self, task: TaskView, state: RunState) -> float`](../../harness/strategy.py#L129) — Hard cap in competition units for the whole next attempt on `task`
- [`Strategy.model_for(self, task: TaskView, state: RunState, attempt: int) -> str`](../../harness/strategy.py#L136) — Qwen model for the next attempt (attempt counts from 1).
- [`Strategy.should_escalate(self, task: TaskView, result: AttemptResult, state: RunState) -> bool`](../../harness/strategy.py#L140) — After a non-verified attempt: try again (next attempt/agent)?
- [`Strategy.should_verify(self, task: TaskView, result: AttemptResult, state: RunState) -> bool`](../../harness/strategy.py#L145) — After an answer that is not verified by tests: spend tokens on an
- [`Strategy.should_diagnose(self, task: TaskView, state: RunState) -> bool`](../../harness/strategy.py#L153) — Before attempting: ask the Executor for an LLM diagnostic
- [`check_strategy(s: object) -> list[str]`](../../harness/strategy.py#L162) — Return a list of contract violations (empty if OK).

## `harness/task_limits.py`

- [`positive_env_float(name: str, default: float) -> float`](../../harness/task_limits.py#L13) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `harness/tasks.py`

- [`Task.ws(self) -> Path`](../../harness/tasks.py#L37) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`scan(tasks_dir: Path) -> list[Task]`](../../harness/tasks.py#L42) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_atomic_write(path: Path, text: str) -> None`](../../harness/tasks.py#L84) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`AnswerStore.__init__(self, out_path: str | None)`](../../harness/tasks.py#L105) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`AnswerStore.write_answer(self, task: Task, answer: str, calls: list | None=None) -> None`](../../harness/tasks.py#L112) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`AnswerStore.record(self, task: Task, calls: list | None=None) -> None`](../../harness/tasks.py#L119) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`AnswerStore._flush(self) -> None`](../../harness/tasks.py#L133) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/analyze_model_routing.py`

- [`merged_reason_trace(run: Path, shards: list[dict]) -> dict`](../../tools/analyze_model_routing.py#L36) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`task_costs(trace: dict, task_ids: set[str]) -> dict[str, float]`](../../tools/analyze_model_routing.py#L49) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`percentile(values: list[float], fraction: float) -> float`](../../tools/analyze_model_routing.py#L58) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`replay_episode(ids, rows, costs, policy, budget)`](../../tools/analyze_model_routing.py#L63) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`analyze(args)`](../../tools/analyze_model_routing.py#L89) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../tools/analyze_model_routing.py#L254) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/compare.py`

- [`free_port() -> int`](../../tools/compare.py#L32) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`run_one(strategy, tasks_dir: Path, truth: Path, mode: str, budget: float, noise: float, seed: int, workdir: Path) -> dict`](../../tools/compare.py#L38) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../tools/compare.py#L98) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/diagnose_sdk.py`

- [`async diagnose()`](../../tools/diagnose_sdk.py#L15) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`async diagnose.send(client, request, **kwargs)`](../../tools/diagnose_sdk.py#L30) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/document_api.py`

- [`first_sentence(node: ast.AST) -> str`](../../tools/document_api.py#L15) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`inventory(path: Path) -> list[tuple[str, int, str, str]]`](../../tools/document_api.py#L22) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`inventory.Collector.visit_ClassDef(self, node: ast.ClassDef) -> None`](../../tools/document_api.py#L29) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`inventory.Collector.visit_FunctionDef(self, node: ast.FunctionDef) -> None`](../../tools/document_api.py#L34) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`inventory.Collector.visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None`](../../tools/document_api.py#L37) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`inventory.Collector._function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None`](../../tools/document_api.py#L40) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`render() -> str`](../../tools/document_api.py#L56) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main() -> None`](../../tools/document_api.py#L86) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/evaluate.py`

- [`score(tasks: Path, truth_path: Path) -> dict`](../../tools/evaluate.py#L20) — Machine-readable result for tools/compare.py.
- [`main()`](../../tools/evaluate.py#L30) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`_evaluate(tasks: Path, truth_path: Path) -> dict`](../../tools/evaluate.py#L36) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/mock_llm.py`

- [`toks(s: str) -> int`](../../tools/mock_llm.py#L30) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`H.log_message(self, *a)`](../../tools/mock_llm.py#L35) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`H._send(self, code, obj)`](../../tools/mock_llm.py#L38) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`H.do_POST(self)`](../../tools/mock_llm.py#L46) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`H.answer(self, req, msgs, tid, tr, rng=None)`](../../tools/mock_llm.py#L92) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`H._wrong(self, exp: str, rng=None) -> str`](../../tools/mock_llm.py#L145) — Independent random error (real models rarely err identically).
- [`main()`](../../tools/mock_llm.py#L155) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main.find(text)`](../../tools/mock_llm.py#L195) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/probe_proxy.py`

- [`effective_max_tokens(model: str, requested: int) -> int`](../../tools/probe_proxy.py#L55) — What harness.llm really sends (thinking models get a higher floor).
- [`async one(llm: LLM, led: BudgetLedger, model, transport, kind)`](../../tools/probe_proxy.py#L63) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`verdict(results: list[dict], models: list[str]) -> list[str]`](../../tools/probe_proxy.py#L117) — Plain-language summary for the team (also stored in the report).
- [`async main()`](../../tools/probe_proxy.py#L160) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/run_controlled.py`

- [`digest_tree(root, exclude=())`](../../tools/run_controlled.py#L30) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`code_digest()`](../../tools/run_controlled.py#L38) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`prepare(args)`](../../tools/run_controlled.py#L46) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`journal_summary(path)`](../../tools/run_controlled.py#L83) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`execute(plan_path)`](../../tools/run_controlled.py#L100) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`score_plan(plan_path, private)`](../../tools/run_controlled.py#L159) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../tools/run_controlled.py#L199) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/score320.py`

- [`probes_from_tests(source, function)`](../../tools/score320.py#L22) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`observe(workspace, module, function, probes, timeout)`](../../tools/score320.py#L46) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`grade_code(candidate, pristine, private, tid, timeout=10)`](../../tools/score320.py#L69) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`evaluate(tasks, source, private, trace=None, timeout=10, task_ids=None)`](../../tools/score320.py#L114) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../tools/score320.py#L158) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/selfcheck.py`

- [`read_file(path: str) -> str`](../../tools/selfcheck.py#L27) — Read a file.

## `tools/stress_compare.py`

- [`run_compare(*, seeds: str, n: int, budget: float, noise: float, infeasible: float, strategies: str, out: Path) -> dict`](../../tools/stress_compare.py#L31) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`total_pct(rows: list[dict]) -> float`](../../tools/stress_compare.py#L54) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main() -> None`](../../tools/stress_compare.py#L59) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/task_factory.py`

- [`gen_math(rnd: random.Random, infeasible: bool)`](../../tools/task_factory.py#L40) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`gen_kb(rnd: random.Random, n_people=30)`](../../tools/task_factory.py#L99) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`write_kb(ws: Path, kb: dict, comps)`](../../tools/task_factory.py#L118) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`gen_search(rnd: random.Random, infeasible: bool)`](../../tools/task_factory.py#L128) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`gen_data(rnd: random.Random, infeasible: bool)`](../../tools/task_factory.py#L182) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`mutate_src(src: str, rnd: random.Random)`](../../tools/task_factory.py#L280) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`gen_coding(rnd: random.Random, infeasible: bool)`](../../tools/task_factory.py#L336) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../tools/task_factory.py#L389) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/validation/common.py`

- [`guard(path)`](../../tools/validation/common.py#L6) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`in_checkout(path)`](../../tools/validation/common.py#L13) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/validation/controls.py`

- [`controls(public, private)`](../../tools/validation/controls.py#L12) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`controls.check(reference, hidden)`](../../tools/validation/controls.py#L25) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../tools/validation/controls.py#L42) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/validation/grade_archive.py`

- [`grade_run(tasks, trace, private, out)`](../../tools/validation/grade_archive.py#L22) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../tools/validation/grade_archive.py#L94) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.

## `tools/validation/run_public.py`

- [`run_public(source, public, inventory, out, task_seconds=30.0, phase_seconds=90.0)`](../../tools/validation/run_public.py#L17) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
- [`main()`](../../tools/validation/run_public.py#L71) — Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке.
