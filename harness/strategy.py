"""Strategy / Executor contract (v1).

A Strategy decides *what* to do with the budget; the Executor does it.
Strategies are pure decision logic: they never call an LLM, never touch
files and never spend tokens themselves.  Everything that costs tokens or
time goes through the Executor, which owns the budget ledger, writes
answers and records every call.

See docs/contracts/strategy.md for the semantics of every field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

CONTRACT_VERSION = "1.0"

# Task status values (hypotheses, not ground truth - see docs).
PENDING = "pending"
VERIFIED = "verified"                    # passed our check (e.g. the task's tests)
ANSWERED_UNVERIFIED = "answered_unverified"
INFEASIBLE_CLAIMED = "infeasible_claimed"
SKIPPED = "skipped"
FAILED = "failed"
STATUSES = (PENDING, VERIFIED, ANSWERED_UNVERIFIED, INFEASIBLE_CLAIMED, SKIPPED, FAILED)

# Spending limits enforced by the Executor (contest units: output + 0.1*input).
MIN_CAP = 50.0             # budget_for() below this means "defer this task now"
DIAG_CAP = 150.0           # hard cap of one should_diagnose() check
VOTE_CAP_DEFAULT = 1200.0  # cap of one should_verify() vote unless Strategy.vote_cap is set

# Deterministic-phase outcome per task.
DET_NONE = "none"                        # no deterministic solver understood the task
DET_ANSWERED = "answered"
DET_INFEASIBLE = "infeasible_claimed"
DET_PARTIAL = "partial"                  # e.g. some functions repaired, tests still fail
DET_MAYBE_INFEASIBLE = "maybe_infeasible"


@dataclass(frozen=True)
class TaskView:
    """Read-only view of one task.  Never contains the reference answer."""
    task_id: str
    type: str                            # math | search | data_analysis | coding | other
    reward: float
    check: str                           # exact_int | exact_str | unittest | ...
    # cheap features (no tokens spent)
    instruction_chars: int = 0
    n_files: int = 0
    files_bytes: int = 0
    det_status: str = DET_NONE
    det_note: str = ""
    # filled by a predictor (Strategy may overwrite its own copy)
    est_cost: float | None = None        # competition units for one attempt
    est_p: float | None = None           # probability that an attempt is correct


@dataclass(frozen=True)
class Call:
    model: str
    transport: str                       # openjiuwen | raw
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost: float                          # competition units = out + 0.1 * in
    sec: float
    tag: str = ""                        # e.g. "math:<id>", "plan:<id>"
    error: str = ""
    accounting: str = "usage"             # zero display tokens may mean unknown
    finish_reason: str = ""


@dataclass(frozen=True)
class AttemptResult:
    """Outcome of one Executor attempt on one task (same shape as results.json)."""
    task_id: str
    attempt: int                         # 1, 2, ...
    kind: str                            # oneshot | agent | diagnose | vote
    model: str
    status: str                          # one of STATUSES
    answer: str | None
    verify: str                          # unittest | det_parse | vote | none
    cost: float                          # competition units spent by this attempt
    sec: float
    calls: tuple[Call, ...] = ()
    note: str = ""


@dataclass
class RunState:
    """Global state, rebuilt by the Executor before every Strategy call."""
    budget_total: float
    spent: float
    remaining: float                     # budget_total - spent - reserved, minus safety reserve
    elapsed: float                       # seconds since start
    time_left: float                     # seconds until the Executor stops starting work
    proxy_dead: bool = False
    status_by_task: dict[str, str] = field(default_factory=dict)
    history: list[AttemptResult] = field(default_factory=list)
    # per task type: {"n": attempts, "verified": n, "cost": units, "sec": seconds}
    type_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    diagnostics: dict[str, dict] = field(default_factory=dict)   # task_id -> result
    unavailable_models: tuple[str, ...] = ()
    # pending tasks the Executor will not start until the next attempt finishes
    # (budget_for() returned < MIN_CAP, or the ledger refused the reservation)
    deferred: tuple[str, ...] = ()
    in_flight: tuple[str, ...] = ()      # pending tasks currently being worked on

    def attempts(self, task_id: str) -> list[AttemptResult]:
        return [a for a in self.history if a.task_id == task_id]


@runtime_checkable
class Strategy(Protocol):
    """Decision policy.  All methods must be fast, deterministic given their
    inputs, and free of side effects."""

    name: str

    def order(self, tasks: list[TaskView], state: RunState) -> list[str]:
        """Task ids to attempt next, best first.  Called again after every
        finished attempt, so priorities can change.  `tasks` holds every
        pending task (including state.deferred and state.in_flight ones);
        the Executor takes the first id that is neither deferred nor in
        flight.  Omitting a task leaves it pending but not attempted now;
        tasks still pending when the run ends become `skipped`."""
        ...

    def budget_for(self, task: TaskView, state: RunState) -> float:
        """Hard cap in competition units for the whole next attempt on `task`
        (all of its LLM calls together).  A value below MIN_CAP defers the
        task until another attempt finishes.  The Executor clips it to
        state.remaining and clamps every call so the attempt cannot exceed it."""
        ...

    def model_for(self, task: TaskView, state: RunState, attempt: int) -> str:
        """Qwen model for the next attempt (attempt counts from 1)."""
        ...

    def should_escalate(self, task: TaskView, result: AttemptResult,
                        state: RunState) -> bool:
        """After a non-verified attempt: try again (next attempt/agent)?"""
        ...

    def should_verify(self, task: TaskView, result: AttemptResult,
                      state: RunState) -> bool:
        """After an answer that is not verified by tests: spend tokens on an
        independent second opinion (vote)?  The vote is capped at
        `getattr(strategy, "vote_cap", VOTE_CAP_DEFAULT)` units and is
        skipped if state.remaining cannot cover that cap."""
        ...

    def should_diagnose(self, task: TaskView, state: RunState) -> bool:
        """Before attempting: ask the Executor for an LLM diagnostic
        (feasibility / cost estimate).  The Executor performs the call,
        charges it with tag plan:<task_id> (at most DIAG_CAP units; skipped
        if state.remaining < DIAG_CAP) and stores the result in
        state.diagnostics[task_id]."""
        ...


def check_strategy(s: object) -> list[str]:
    """Return a list of contract violations (empty if OK)."""
    problems = []
    if not isinstance(getattr(s, "name", None), str):
        problems.append("missing str attribute 'name'")
    for m in ("order", "budget_for", "model_for", "should_escalate", "should_verify",
              "should_diagnose"):
        if not callable(getattr(s, m, None)):
            problems.append(f"missing method {m}()")
    vc = getattr(s, "vote_cap", VOTE_CAP_DEFAULT)
    if not isinstance(vc, (int, float)) or vc < 0:
        problems.append("attribute 'vote_cap' must be a non-negative number")
    return problems
