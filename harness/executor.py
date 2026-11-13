"""Executor that runs the LLM phase through a Strategy (contract v1.0).

Spending: every attempt / vote / diagnosis runs inside llm.cap_scope, so
its LLM calls are clamped to the cap; the ledger checks the global budget.

The deterministic phase (free) is done by Harness before this runs.  Here:
up to 5 workers (LLM calls limited to LLM_CONCURRENCY, default 1, and LLM_RPM, default 30); before every attempt the Strategy re-orders the pending
tasks; each attempt is one AttemptResult in state.history.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from . import llm_solvers as L
from .llm import LLMUnavailable, MODEL_FAST, cap_scope
from .log import log
from .task_limits import TASK_CAP
from .strategy import (ANSWERED_UNVERIFIED, AttemptResult, Call, DET_ANSWERED, DET_INFEASIBLE,
                       DET_MAYBE_INFEASIBLE, DET_NONE, DET_PARTIAL, DIAG_CAP, FAILED,
                       INFEASIBLE_CLAIMED, MIN_CAP, PENDING, RunState, SKIPPED, TaskView,
                       VERIFIED, VOTE_CAP_DEFAULT)

_DET_MAP = {"answer": DET_ANSWERED, "fixed": DET_ANSWERED, "already_pass": DET_ANSWERED,
            "infeasible": DET_INFEASIBLE, "maybe_infeasible": DET_MAYBE_INFEASIBLE,
            "partial": DET_PARTIAL}

ONESHOT = {"math": L.solve_math, "data_analysis": L.solve_data, "search": L.solve_search}


class StrategyExecutor:
    def __init__(self, harness, strategy, workers: int = 5):
        self.h = harness
        self.s = strategy
        self.workers = workers
        self.history: list[AttemptResult] = []
        self.diagnostics: dict[str, dict] = {}
        self.type_stats: dict[str, dict[str, float]] = {}
        # task_id -> number of finished attempts when it was deferred; it is
        # offered again once another attempt finishes (docs: state transitions)
        self.deferred: dict[str, int] = {}
        self.inflight: set[str] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------- views
    def view(self, t) -> TaskView:
        from .pipeline import type_of
        n_files = size = 0
        try:
            for p in t.ws.rglob("*"):
                if p.is_file():
                    n_files += 1
                    size += p.stat().st_size
        except OSError:
            pass
        det = t.raw.get("_det")
        return TaskView(task_id=t.task_id, type=type_of(t), reward=t.reward, check=t.check,
                        instruction_chars=len(t.instruction), n_files=n_files,
                        files_bytes=size if type_of(t) != "coding" else
                        sum(p.stat().st_size for p in t.ws.glob("*.py")),
                        det_status=_DET_MAP.get(det[0], DET_NONE) if det else DET_NONE,
                        det_note=(det[2] if det and len(det) > 2 else "") or "")

    def state(self) -> RunState:
        led = self.h.ledger
        return RunState(
            budget_total=led.total, spent=led.spent, remaining=max(0.0, led.usable()),
            elapsed=self._elapsed(), time_left=self.h.time_left(), proxy_dead=led.dead,
            status_by_task={t.task_id: t.status for t in self.h.tasks},
            history=list(self.history), type_stats={k: dict(v) for k, v in self.type_stats.items()},
            diagnostics=dict(self.diagnostics),
            unavailable_models=tuple(sorted(self.h.llm.bad_models)),
            deferred=tuple(sorted(i for i in self.deferred if not self._eligible(i))),
            in_flight=tuple(sorted(self.inflight)))

    def _eligible(self, task_id: str) -> bool:
        ep = self.deferred.get(task_id)
        return ep is None or ep < len(self.history)

    def _defer(self, task_id: str, why: str) -> None:
        self.deferred[task_id] = len(self.history)
        log(f"{task_id}: deferred ({why})")

    @staticmethod
    def _elapsed() -> float:
        from .log import elapsed
        return elapsed()

    def _calls_since(self, n0: int, task_id: str) -> tuple[Call, ...]:
        out = []
        for c in self.h.ledger.log[n0:]:
            tag = c.get("tag", "")
            if tag.split(":")[1:2] != [task_id]:
                continue
            out.append(Call(model=c.get("model", ""), transport=c.get("transport", ""),
                            input_tokens=int(c.get("in") or 0), output_tokens=int(c.get("out") or 0),
                            reasoning_tokens=int(c.get("reason") or 0), cost=float(c.get("cost", 0)),
                            sec=float(c.get("sec", 0) or 0), tag=tag, error=c.get("error", ""),
                            accounting=c.get("accounting", "usage"),
                            finish_reason=c.get("finish_reason", "")))
        return tuple(out)

    # ---------------------------------------------------------- attempts
    async def _attempt(self, t, view: TaskView, attempt: int, model: str, cap: float,
                       *, rescue: bool = False) -> AttemptResult:
        n0, c0, t0 = len(self.h.ledger.log), t.cost, time.time()
        ty = view.type
        kind = "oneshot"
        r = None
        try:
            if ty == "coding":
                if rescue:
                    r = await L.solve_coding(self.h.llm, t, model=model, attempts=1,
                                             min_output_tokens=1800)
                elif attempt == 1:
                    det = t.raw.get("_det")
                    start = det[1] if det and det[0] == "partial" else None
                    r = await L.solve_coding(self.h.llm, t, model=model, start_files=start)
                else:
                    kind = "agent"
                    r = await L.agent_solve(self.h.llm, t, cap=cap, model=model,
                                            max_steps=getattr(self.s, "max_tool_steps", 12),
                                            stop_repeated=getattr(self.s, "stop_repeated_tools", False))
            elif ty in ONESHOT and (attempt <= 2 or rescue):
                options = ({"repairs": self.s.execution_repairs}
                           if ty in ("math", "data_analysis") and getattr(self.s, "execution_repairs", 0)
                           else {})
                if rescue and ty in ("math", "data_analysis"):
                    options["max_tokens"] = 1800
                r = await ONESHOT[ty](self.h.llm, t, model=model, **options)
            else:
                kind = "agent"
                r = await L.agent_solve(self.h.llm, t, cap=cap, model=model,
                                            max_steps=getattr(self.s, "max_tool_steps", 12),
                                            stop_repeated=getattr(self.s, "stop_repeated_tools", False))
        except LLMUnavailable as e:
            log(f"{t.task_id}: LLM unavailable ({e})")
            self.h._calls_for(t)
            if self.h.ledger.dead:
                # Transport/usage uncertainty is not evidence that the solver
                # failed. Preserve its conservative debit, but do not expose
                # it to scheduling statistics or online learning as an
                # AttemptResult.
                r = ("unavailable", None, f"infrastructure halt: {e}")
            elif str(e) in ("budget", "cap") and t.cost - c0 <= 0:
                r = ("nobudget", None, f"refused before spending: {e}")
            elif str(e) == "cap":
                r = ("error", None, "attempt cap reached")
            elif self.h.ledger.dead and t.cost == c0:
                r = ("nobudget", None, f"llm unavailable: {e}")
            else:
                r = ("error", None, f"llm unavailable: {e}")
        self.h._calls_for(t)
        status, answer, verify, note = FAILED, None, "none", ""
        if r is not None and r[0] == "nobudget":
            status, note = SKIPPED, r[2]
        elif r is not None and r[0] == "unavailable":
            status, note = SKIPPED, r[2]
        elif r is None or r[0] == "error":
            note = (r[2] if r else "no result") or ""
        elif r[0] == "answer" and r[1]:
            self.h.accept_answer(t, r[1], f"llm-{kind}", verify="none")
            status, answer = ANSWERED_UNVERIFIED, r[1]
        elif r[0] == "fixed":
            if self.h.accept_code(t, r[1], f"llm-{kind}"):
                status, answer, verify = VERIFIED, "DONE", "unittest"
            else:
                note = "fix did not verify in place"
        elif r[0] == "infeasible":
            status, note = INFEASIBLE_CLAIMED, r[2] or "model: infeasible"
        res = AttemptResult(task_id=t.task_id, attempt=attempt,
                            kind="rescue" if rescue else kind, model=model,
                            status=status, answer=answer, verify=verify, cost=t.cost - c0,
                            sec=round(time.time() - t0, 2), calls=self._calls_since(n0, t.task_id),
                            note=note[:200])
        st = self.type_stats.setdefault(ty, {"n": 0, "verified": 0, "cost": 0.0, "sec": 0.0})
        if status != SKIPPED:
            st["n"] += 1
            st["cost"] += res.cost
            st["sec"] += res.sec
        if status == VERIFIED:
            st["verified"] += 1
        return res

    @staticmethod
    def _task_left(t) -> float:
        """Remaining aggregate task budget across attempts, votes and diagnosis.

        t.cost is updated after each LLM request, including failed requests.
        The worker holds one task at a time, so a task has no concurrent
        attempt/vote in flight. Individual scopes reserve each call separately.
        """
        return max(0.0, TASK_CAP - t.cost)

    async def _vote(self, t, view: TaskView, first: AttemptResult, *,
                    cap: float | None = None) -> AttemptResult | None:
        """Independent second opinion; change the answer only on a 2-of-3 majority."""
        solver = ONESHOT.get(view.type)
        if solver is None:
            return None
        models = list(getattr(self.s, "vote_models", ())) or [MODEL_FAST]
        configured = (float(getattr(self.s, "vote_cap", VOTE_CAP_DEFAULT))
                      if cap is None else max(0.0, float(cap)))
        vcap = min(configured,
                   self._task_left(t), max(0.0, self.h.ledger.usable()))
        if vcap < MIN_CAP:
            return None
        n0, c0, t0 = len(self.h.ledger.log), t.cost, time.time()
        votes = [t.answer]
        try:
            with cap_scope(vcap):
                r2 = await solver(self.h.llm, t, model=models[0])
                a2 = r2[1] if r2 and r2[0] == "answer" else None
                votes.append(a2)
                if a2 != t.answer and len(models) > 1:
                    r3 = await solver(self.h.llm, t, model=models[1])
                    votes.append(r3[1] if r3 and r3[0] == "answer" else None)
        except LLMUnavailable:
            self.h._calls_for(t)
            if len(votes) < 2 and t.cost == c0:
                return None     # no second opinion: keep the answer as is
        self.h._calls_for(t)
        cand = [v for v in votes if v]
        best = max(set(cand), key=votes.count) if cand else t.answer
        changed = best != t.answer and votes.count(best) >= 2
        if changed:
            log(f"{t.task_id}: vote changed {t.answer!r} -> {best!r}")
            self.h.accept_answer(t, best, t.solver + "+vote", verify="vote")
        else:
            if votes.count(t.answer) >= 2:
                t.verify = "vote"
            self.h.record(t)
        return AttemptResult(task_id=t.task_id, attempt=first.attempt, kind="vote",
                             model=",".join(models), status=t.status, answer=t.answer,
                             verify=t.verify, cost=t.cost - c0, sec=round(time.time() - t0, 2),
                             calls=self._calls_since(n0, t.task_id),
                             note=f"votes={votes}")

    async def _run_endgame(self) -> None:
        """Spend surplus on ranked verification only after the first pass.

        This is deliberately opt-in and is not part of Strategy contract v1.
        It never competes with pending work.  Truncated responses get a
        separate bounded rescue ceiling; votes retain the first-pass cap.
        Both preserve the strategy reserve and the ledger safety reserve.
        """
        if not getattr(self.s, "endgame_enabled", False):
            return
        if self.h.ledger.dead or any(t.status == PENDING for t in self.h.tasks):
            return
        reserve = max(0.0, float(getattr(self.s, "endgame_reserve", 0.0)))
        min_time = max(60.0, float(getattr(self.s, "endgame_min_time", 120.0)))
        cap = max(MIN_CAP, float(getattr(
            self.s, "endgame_vote_cap", getattr(self.s, "vote_cap", VOTE_CAP_DEFAULT)
        )))
        await self._rescue_truncated(reserve, min_time)
        if self.h.ledger.dead:
            return
        candidates = [
            t for t in self.h.tasks
            if t.status == ANSWERED_UNVERIFIED
            and t.verify == "none"
            and t.solver.startswith("llm")
            and self.view(t).type in ONESHOT
        ]
        if not candidates:
            return
        views = {t.task_id: self.view(t) for t in candidates}
        orderer = getattr(self.s, "endgame_order", None)
        raw_order = (orderer(list(views.values()), self.state())
                     if callable(orderer)
                     else [t.task_id for t in sorted(candidates,
                                                    key=lambda item: (-item.reward,
                                                                      item.task_id))])
        allowed = set(views)
        order = list(dict.fromkeys(task_id for task_id in raw_order
                                   if task_id in allowed))
        by_id = {t.task_id: t for t in candidates}
        checked = 0
        start_spent = self.h.ledger.spent
        for task_id in order:
            available = max(0.0, self.h.ledger.usable() - reserve)
            if (self.h.ledger.dead or self.h.time_left() < min_time
                    or available < MIN_CAP):
                break
            t = by_id[task_id]
            allowance = min(cap, self._task_left(t), available)
            if allowance < MIN_CAP:
                continue
            first = next((attempt for attempt in reversed(self.history)
                          if attempt.task_id == task_id and attempt.kind != "vote"
                          and attempt.status == ANSWERED_UNVERIFIED), None)
            if first is None:
                continue
            try:
                result = await self._vote(t, views[task_id], first, cap=allowance)
            except Exception as error:  # noqa: BLE001 - isolate one verification
                log(f"{task_id}: endgame verification failed: {error}")
                continue
            if result is not None:
                self.history.append(result)
                checked += 1
        log(f"endgame: checked {checked}/{len(order)}, spent "
            f"{self.h.ledger.spent - start_spent:.0f}, kept {reserve:.0f} reserve")

    async def _rescue_truncated(self, reserve: float, min_time: float) -> None:
        """Retry measured, truncated outputs once while surplus remains.

        A transport error or unknown usage halts the ledger and can never enter
        this path.  Each task has one rescue, its own expanded ceiling, and a
        fresh capped reservation.  Earlier answers are never overwritten here.
        """
        if not getattr(self.s, "endgame_rescue_enabled", False):
            return
        ceiling = max(TASK_CAP, float(getattr(self.s, "endgame_rescue_task_cap", TASK_CAP)))
        attempt_cap = max(MIN_CAP, float(getattr(self.s, "endgame_rescue_attempt_cap", MIN_CAP)))
        candidates = []
        for t in self.h.tasks:
            if t.status != FAILED or self.view(t).type not in (*ONESHOT, "coding"):
                continue
            last = next((a for a in reversed(self.history)
                         if a.task_id == t.task_id and a.kind != "vote"), None)
            if (last is None or last.status != FAILED or not last.calls
                    or any(a.task_id == t.task_id and a.kind == "rescue"
                           for a in self.history)
                    or "output cap: truncated response" not in last.note
                    or any(c.accounting != "usage" or c.error for c in last.calls)):
                continue
            candidates.append((t, last))
        candidates.sort(key=lambda pair: (-pair[0].reward, pair[0].task_id))
        rescued = 0
        start_spent = self.h.ledger.spent
        for t, last in candidates:
            available = max(0.0, self.h.ledger.usable() - reserve)
            if (self.h.ledger.dead or self.h.time_left() < min_time
                    or available < MIN_CAP):
                break
            allowance = min(attempt_cap, ceiling - t.cost, available)
            if allowance < MIN_CAP:
                continue
            view = self.view(t)
            # A no-reasoning alternate makes room for a complete response when
            # the first reasoning model exhausted its output allocation.
            model = getattr(self.s, "endgame_rescue_model", MODEL_FAST)
            if model in self.h.llm.bad_models:
                model = MODEL_FAST
            try:
                with cap_scope(allowance):
                    result = await self._attempt(t, view, last.attempt + 1, model,
                                                 allowance, rescue=True)
            except Exception as error:  # noqa: BLE001 - preserve other tasks
                log(f"{t.task_id}: endgame rescue failed: {error}")
                continue
            if self.h.ledger.dead:
                self.h.mark(t, SKIPPED, result.note or "infrastructure halt")
                break
            if result.status == SKIPPED:
                continue
            self.history.append(result)
            rescued += 1
            if result.status == INFEASIBLE_CLAIMED:
                self.h.mark(t, INFEASIBLE_CLAIMED, result.note)
            elif result.status == FAILED:
                self.h.mark(t, FAILED, result.note or "rescue failed")
        log(f"endgame: rescued {rescued}/{len(candidates)}, spent "
            f"{self.h.ledger.spent - start_spent:.0f}")

    async def _diagnose(self, t, view: TaskView) -> None:
        """Short LLM feasibility/cost check, charged with tag plan:<id>."""
        prompt = ("Assess this task without solving it. Reply with JSON only: "
                  '{"feasible": <probability 0..1 that it can be solved exactly from the '
                  'given data>, "difficulty": "easy|medium|hard"}.\n\nTask: '
                  + L.clean_instruction(t.instruction)[:1500])
        dcap = min(DIAG_CAP, self._task_left(t),
                   max(0.0, self.h.ledger.usable()))
        if dcap < MIN_CAP:
            return
        try:
            with cap_scope(dcap):
                r = await self.h.llm.chat([{"role": "user", "content": prompt}],
                                          model=MODEL_FAST, max_tokens=60,
                                          tag=f"plan:{t.task_id}")
            t.cost += r["cost"]
            m = re.search(r"\{.*\}", r["content"] or "", re.S)
            d = json.loads(m.group(0)) if m else {"raw": (r["content"] or "")[:200]}
        except (LLMUnavailable, ValueError) as e:
            d = {"error": str(e)[:200]}
        self.h._calls_for(t)
        self.diagnostics[t.task_id] = d

    # -------------------------------------------------------------- loop
    async def _process(self, t) -> None:
        view = self.view(t)
        state = self.state()
        if t.task_id not in self.diagnostics and self.s.should_diagnose(view, state):
            await self._diagnose(t, view)
            state = self.state()
        cap = float(self.s.budget_for(view, state))
        # Enforce the aggregate ceiling independently of Strategy.budget_for.
        # Earlier attempts and any diagnosis already contribute to t.cost.
        cap = min(cap, self._task_left(t), max(0.0, self.h.ledger.usable()))
        if cap < MIN_CAP:
            self._defer(t.task_id, f"cap {cap:.0f} < MIN_CAP")
            return
        attempt = 1 + sum(1 for a in self.history if a.task_id == t.task_id and a.kind != "vote")
        model = self.s.model_for(view, state, attempt)
        with cap_scope(cap):
            res = await self._attempt(t, view, attempt, model, cap)
        if res.status == SKIPPED:
            if res.cost > 0 or getattr(self.h.ledger, "dead", False):
                # An uncertain physical dispatch was charged, but it is not a
                # solver outcome. Persist the task and stop without adding it
                # to history, type_stats or Strategy.observe().
                self.h.mark(t, SKIPPED, res.note)
            else:
                # Refusal before dispatch may become eligible after another
                # attempt changes the available budget.
                self._defer(t.task_id, res.note)
            return
        self.deferred.pop(t.task_id, None)
        self.history.append(res)
        state = self.state()
        # Explicit post-action online learning. This is never called for
        # private-grader results (which are not exposed during the run).
        observer = getattr(self.s, "observe", None)
        if observer is not None:
            try:
                observer(view, res, state)
            except (ArithmeticError, ValueError, OverflowError) as e:
                log(f"{view.task_id}: online learning disabled for sample: {e}")
        if res.status == ANSWERED_UNVERIFIED and self.s.should_verify(view, res, state):
            v = await self._vote(t, view, res)
            if v:
                self.history.append(v)
            return
        if res.status in (VERIFIED, ANSWERED_UNVERIFIED):
            return
        if self.s.should_escalate(view, res, state):
            return                      # stays pending; order() decides when to retry
        if res.status == INFEASIBLE_CLAIMED:
            claims = sum(1 for a in self.history
                         if a.task_id == t.task_id and a.status == INFEASIBLE_CLAIMED)
            why = ("det+llm agree" if view.det_status == DET_MAYBE_INFEASIBLE
                   else f"model claims={claims}")
            self.h.mark(t, INFEASIBLE_CLAIMED, why)
        else:
            self.h.mark(t, FAILED, res.note or "attempts exhausted")

    def _stop(self) -> bool:
        return self.h.ledger.dead or self.h.time_left() < 60

    async def _worker(self, wid: int) -> None:
        while not self._stop():
            async with self._lock:
                views = [self.view(t) for t in self.h.tasks if t.status == PENDING]
                order = self.s.order(views, self.state())
                pending = {v.task_id for v in views}
                pick = next((i for i in order if i in pending and i not in self.inflight
                             and self._eligible(i)), None)
                busy = bool(self.inflight)
                if pick is not None:
                    self.inflight.add(pick)
            if pick is None:
                if busy:
                    await asyncio.sleep(0.2)   # others may still release work
                    continue
                return
            t = next(x for x in self.h.tasks if x.task_id == pick)
            try:
                await self._process(t)
            except Exception as e:  # noqa: BLE001 - never kill the run
                log(f"{t.task_id}: executor error {type(e).__name__}: {e}")
                self.h.mark(t, FAILED, f"executor error: {e}")
            finally:
                self.inflight.discard(pick)

    async def run(self) -> None:
        if self.h.llm.enabled:
            log(f"executor: strategy={self.s.name}, workers={self.workers}")
            # A true two-phase preflight: finish analysis before solving begins.
            # Disabled by default and accounts for all analysis tokens.
            if getattr(self.s, "preflight_enabled", False):
                from .preflight import preflight_all
                self.diagnostics.update(await preflight_all(self))
            await asyncio.gather(*(self._worker(i) for i in range(self.workers)))
        for t in self.h.tasks:
            # a held-back deterministic fix is better than no answer
            if t.status != VERIFIED and (t.raw.get("_det") or (None,))[0] == "weak_fix":
                await asyncio.to_thread(self.h.apply_weak_fix, t)
        if self.h.llm.enabled:
            await self._run_endgame()
        for t in self.h.tasks:
            if t.status == PENDING:
                self.h.mark(t, SKIPPED, "no budget/time or strategy skipped it")
        plan = sum(c.get("cost", 0) for c in self.h.ledger.log
                   if str(c.get("tag", "")).startswith("plan:"))
        log(f"executor done: {len(self.history)} attempts, spent {self.h.ledger.spent:.0f} "
            f"(planning {plan:.0f})")
