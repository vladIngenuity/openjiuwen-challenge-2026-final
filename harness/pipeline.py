"""Scheduler: deterministic first, then LLM in expected-reward-per-token order."""
from __future__ import annotations

import asyncio
import ctypes
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import llm_solvers as L, sandbox
from .budget import BudgetLedger
from .llm import LLM, LLMUnavailable, MODEL_FAST, MODEL_FAST_ALT, MODEL_REASON
from .log import elapsed, log
from .solvers import coding_solver, data_solver, math_solver, search_solver
from .tasks import AnswerStore, Task, _atomic_write, scan

ANSWERED = ("verified", "answered_unverified")
TIME_LIMIT = float(os.environ.get("HARNESS_TIME_LIMIT", "3300"))  # stop new work at 55 min


def _env_seconds(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, default))
    except ValueError:
        return default
    return v if v > 0 else default


# Limits of the free (0-token) phase, so that it cannot eat the contest time:
# one coding repair and the whole phase.  A task that runs out of time is not
# guessed - it goes to the model.
DET_TASK_SECONDS = _env_seconds("HARNESS_DET_TASK_SECONDS", 30)
DET_PHASE_SECONDS = _env_seconds("HARNESS_DET_PHASE_SECONDS", 90)
DET_CODING = os.environ.get("HARNESS_DET_CODING", "fallback").strip().lower()
# Prior success probabilities / costs for one-shot LLM attempts (updated online)
PRIOR_P = {"math": 0.85, "data_analysis": 0.8, "search": 0.85, "coding": 0.65}
PRIOR_C = {"math": 160, "data_analysis": 260, "search": 220, "coding": 700}


def type_of(t: Task) -> str:
    tt = t.task_type
    if tt.startswith("data"):
        return "data_analysis"
    if tt.startswith("code") or tt.startswith("coding") or tt.startswith("program"):
        return "coding"
    if tt.startswith("search") or tt.startswith("retriev"):
        return "search"
    if tt.startswith("math") or tt.startswith("arith"):
        return "math"
    return tt


class Harness:
    def __init__(self, tasks_dir: Path, out_path: str | None, strategy: str = "baseline"):
        self.strategy_name = strategy
        self.tasks_dir = tasks_dir
        self.tasks = scan(tasks_dir)
        self.ledger = BudgetLedger()
        self.llm = LLM(self.ledger, time_left=self.time_left)
        self.store = AnswerStore(out_path)
        self.det_deadline = float("inf")
        self.stats = {k: {"n": 0, "ok": 0, "cost": 0.0} for k in PRIOR_P}
        log(f"{len(self.tasks)} tasks, budget {self.ledger.total:.0f}, "
            f"LLM {'on' if self.llm.enabled else 'OFF'}")

    # ------------------------------------------------------------ persistence
    def _calls_for(self, t: Task) -> list[dict]:
        calls = [c for c in self.ledger.log if c.get("tag", "").split(":")[1:2] == [t.task_id]]
        t.cost = sum(c["cost"] for c in calls)
        return calls

    def record(self, t: Task):
        self.store.record(t, self._calls_for(t))

    def accept_answer(self, t: Task, answer: str, solver: str, note: str = "",
                      verify: str = "none"):
        """verify: unittest (tests pass) | det_parse | vote | none.
        Only unittest counts as verified; everything else is an unverified
        candidate - its correctness is unknown until graded."""
        t.status = "verified" if verify == "unittest" else "answered_unverified"
        t.solver, t.note, t.verify = solver, note, verify
        self.store.write_answer(t, answer, self._calls_for(t))
        log(f"✔ {t.task_id} [{solver}] = {answer!r} (r={t.reward:g}, cost={t.cost:.0f})")

    def record_code(self, t: Task, solver: str, note: str) -> None:
        t.status, t.verify, t.solver, t.note = "verified", "unittest", solver, note
        # Compatibility marker at task root only. Grading still executes code;
        # DONE by itself is never evidence of correctness.
        self.store.write_answer(t, "DONE", self._calls_for(t))

    def accept_code(self, t: Task, files: dict, solver: str, note: str = "") -> bool:
        test_file, targets = coding_solver.locate(t.instruction, t.ws)
        allowed = {p.relative_to(t.ws).as_posix() for p in targets}
        if not test_file or not files or not files.keys() <= allowed:
            return False

        # Stage on the same filesystem. With a flat legacy workspace the full
        # task directory is exchanged, including task.json and prior outputs.
        ws = t.ws
        try:
            with tempfile.TemporaryDirectory(prefix=".patch-", dir=ws.parent,
                                             ignore_cleanup_errors=True) as temp:
                stage = Path(temp) / "workspace"
                sandbox.copy_inputs(ws, stage, skip={"__pycache__", ".git"}, preserve_mode=True)
                for name, src in files.items():
                    _atomic_write(stage / name, src)
                with tempfile.TemporaryDirectory(prefix="verify-") as verification:
                    checked = Path(verification)
                    sandbox.copy_inputs(stage, checked)
                    ok, _ = coding_solver.run_tests(checked, checked / test_file.relative_to(ws),
                                                   min(60, self.time_left()))
                if not ok:
                    return False
                if len(files) == 1:
                    name = next(iter(files))
                    os.replace(stage / name, ws / name)
                else:
                    libc = ctypes.CDLL(None, use_errno=True)
                    exchange = libc.renameat2
                    exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                                         ctypes.c_char_p, ctypes.c_uint]
                    if exchange(-100, os.fsencode(stage), -100, os.fsencode(ws), 2):
                        error = ctypes.get_errno()
                        raise OSError(error, os.strerror(error))
        except (OSError, ValueError, AttributeError) as e:
            log(f"✘ {t.task_id}: cannot publish verified patch: {e}")
            return False
        self.record_code(t, solver, note)
        return True

    def mark(self, t: Task, status: str, note: str):
        t.status, t.note = status, note
        self.record(t)
        log(f"· {t.task_id}: {status} ({note[:120]})")

    # ------------------------------------------------------- deterministic
    def deterministic(self, t: Task):
        import time as _time
        t.t_start = _time.time()
        ty = type_of(t)
        if ty in os.environ.get("HARNESS_DISABLE_DET", "").split(","):
            return None
        try:
            if ty == "math":
                r = math_solver.solve(t.instruction)
                if r:
                    return ("answer", r[0], r[1])
            elif ty == "search":
                return search_solver.solve(t.instruction, t.ws)
            elif ty == "data_analysis":
                return data_solver.solve(t.instruction, t.ws)
            elif ty == "coding":
                left = min(DET_TASK_SECONDS, self.det_deadline - elapsed(), self.time_left())
                if left < 2:
                    return None      # free phase is out of time: leave it to the model
                r = coding_solver.repair(t.instruction, t.ws, max_seconds=left)
                if r["status"] == "fixed":
                    # Private validation on authored tasks (PR #20): 6 repairs passed
                    # the public tests, 1 passed the hidden ones.  So when the model
                    # is available it goes first and the free repair is only the
                    # fallback (HARNESS_DET_CODING=first restores the old order,
                    # except for deletion-only repairs).
                    hold = r.get("weak") or DET_CODING != "first"
                    if hold and self.llm.enabled and self.strategy_name != "legacy":
                        return ("weak_fix", r["files"], r["note"])
                    return ("fixed", r["files"], r["note"])
                if r["status"] == "already_pass":
                    return ("already_pass", None, r["note"])
                if r["status"] == "partial":
                    return ("partial", r.get("files") or {}, r["note"])
        except Exception as e:  # noqa: BLE001
            log(f"{t.task_id}: deterministic solver crashed: {type(e).__name__}: {e}")
        return None

    def apply_weak_fix(self, t: Task) -> bool:
        """Fallback for a coding task the model did not solve: publish the
        deterministic fix that was held back as weak evidence."""
        det = t.raw.get("_det")
        if not det or det[0] != "weak_fix" or t.status == "verified":
            return False
        return self.accept_code(t, det[1], "deterministic-apr-weak", det[2])

    def phase_deterministic(self):
        # Benchmark-only stress mode: isolate scheduling by removing free solutions.
        # Default/contest execution always retains deterministic solvers.
        if os.environ.get('HARNESS_BENCHMARK_STRESS') == '1' and os.environ.get('HARNESS_STRESS_SKIP_DETERMINISTIC') == '1':
            log('BENCHMARK ONLY: deterministic phase disabled for scheduler stress test')
            return
        self.det_deadline = elapsed() + min(DET_PHASE_SECONDS, max(0.0, self.time_left()) * 0.25)
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit fast, text-only tasks first and publish each result when
            # ready, even while other workers are still repairing code.
            tasks = sorted(self.tasks, key=lambda t: type_of(t) == "coding")
            pending = {executor.submit(self.deterministic, t): t for t in tasks}
            for completed in as_completed(pending):
                t = pending[completed]
                r = completed.result()
                t.raw["_det"] = r
                if r is None:
                    continue
                kind = r[0]
                if kind == "answer" and r[1] is not None:
                    ans = L.normalize(str(r[1]), t.check)
                    if ans is not None:
                        try:
                            self.accept_answer(t, ans, "deterministic", r[2], verify="det_parse")
                        except OSError as error:
                            self.mark(t, "failed", f"cannot save answer: {error}")
                elif kind == "fixed":
                    if not self.accept_code(t, r[1], "deterministic-apr", r[2]):
                        t.raw["_det"] = None
                elif kind == "already_pass":
                    self.record_code(t, "deterministic", r[2])
                elif kind == "infeasible":
                    self.mark(t, "infeasible_claimed", r[2])

    # ------------------------------------------------------------ LLM phase
    def p_success(self, t: Task) -> float:
        ty = type_of(t)
        s = self.stats.get(ty)
        p0 = PRIOR_P.get(ty, 0.5)
        # online update only where correctness is observable (coding: tests);
        # for other types an answer's correctness is unknown during the run
        if ty == "coding" and s and s["n"]:
            p0 = (p0 * 2 + s["ok"]) / (2 + s["n"])
        det = t.raw.get("_det")
        if det and det[0] == "maybe_infeasible":
            p0 *= 0.35
        return p0

    def est_cost(self, t: Task) -> float:
        ty = type_of(t)
        s = self.stats.get(ty)
        c = PRIOR_C.get(ty, 1500)
        if ty == "coding":
            try:
                size = sum(p.stat().st_size for p in t.ws.glob("*.py"))
                c = 0.1 * (size + 2500) / 3 + 0.5 * size / 3 + 150
            except OSError:
                pass
        if s and s["n"]:
            c = (c + s["cost"]) / (1 + s["n"])
        return max(50.0, c)

    async def attempt_cheap(self, t: Task):
        ty = type_of(t)
        before = t.cost
        r = None
        unavailable = False
        try:
            if ty == "math":
                r = await L.solve_math(self.llm, t)
            elif ty == "data_analysis":
                r = await L.solve_data(self.llm, t)
            elif ty == "search":
                r = await L.solve_search(self.llm, t)
            elif ty == "coding":
                det = t.raw.get("_det")
                start = det[1] if det and det[0] == "partial" else None
                r = await L.solve_coding(self.llm, t, start_files=start)
            else:
                r = await L.agent_solve(self.llm, t, cap=self.task_cap(t))
        except LLMUnavailable as e:
            unavailable = True
            log(f"{t.task_id}: LLM unavailable ({e})")
            return "nobudget"
        finally:
            self._calls_for(t)
            # Unknown transport/usage outcomes retain their conservative cost,
            # but must not train the legacy solver statistics as failures.
            observed_action = r is not None or (t.cost > before and not self.ledger.dead)
            if ty in self.stats and observed_action and not (unavailable and self.ledger.dead):
                st = self.stats[ty]
                st["n"] += 1
                st["cost"] += t.cost - before
        return self._consume(t, r, "llm-oneshot")

    def _consume(self, t: Task, r, solver: str) -> str:
        ty = type_of(t)
        if r is None or r[0] == "error":
            t.note = (r[2] if r else "no result")[:200]
            return "failed"
        if r[0] == "answer" and r[1]:
            # an answer was produced; its correctness is unknown here, so it
            # does NOT update the success estimate (see p_success)
            self.accept_answer(t, r[1], solver, verify="none")
            return "ok"
        if r[0] == "fixed":
            if self.accept_code(t, r[1], solver):
                if ty in self.stats:
                    self.stats[ty]["ok"] += 1   # verified by the task's tests
                return "ok"
            return "failed"
        if r[0] == "infeasible":
            t.raw["_llm_infeasible"] = t.raw.get("_llm_infeasible", 0) + 1
            return "infeasible"
        return "failed"

    def task_cap(self, t: Task) -> float:
        open_tasks = [x for x in self.tasks if x.status == "pending"]
        share = self.ledger.usable() / max(1, len(open_tasks))
        return max(800.0, min(6000.0, share * 2.5))

    def time_left(self) -> float:
        return TIME_LIMIT - elapsed()

    async def run_queue(self, tasks, fn, label):
        """Run `fn` over tasks in order with up to 5 in flight."""
        sem = asyncio.Semaphore(5)

        async def one(t):
            async with sem:
                if self.ledger.dead or self.time_left() < 60 or t.status != "pending":
                    return
                if self.ledger.usable() < self.est_cost(t) * 0.6:
                    self.mark(t, "skipped", "insufficient budget")
                    return
                await fn(t)

        await asyncio.gather(*(one(t) for t in tasks))
        log(f"{label} done: spent {self.ledger.spent:.0f}/{self.ledger.total:.0f}")

    async def phase_llm(self):
        if not self.llm.enabled:
            return
        pending = [t for t in self.tasks if t.status == "pending"]
        pending.sort(key=lambda t: -(t.reward * self.p_success(t) / self.est_cost(t)))

        async def cheap(t):
            res = await self.attempt_cheap(t)
            if res == "infeasible":
                det = t.raw.get("_det")
                if det and det[0] == "maybe_infeasible":
                    self.mark(t, "infeasible_claimed", "det+llm agree: " + det[2])
            elif res == "failed":
                log(f"{t.task_id}: one-shot failed ({t.note[:100]})")

        await self.run_queue(pending, cheap, "phase B (one-shot)")

        # Phase C: escalate unsolved tasks to the tool agent (bigger cap),
        # highest value first; tasks the model called infeasible go last.
        pending = [t for t in self.tasks if t.status == "pending"]
        pending.sort(key=lambda t: (t.raw.get("_llm_infeasible", 0),
                                    -t.reward / self.est_cost(t)))

        async def escalate(t):
            cap = self.task_cap(t)
            # second one-shot with a different model is cheap and decorrelated
            try:
                ty = type_of(t)
                if ty == "coding":
                    r = await L.agent_solve(self.llm, t, cap=cap)
                elif ty in ("math", "data_analysis", "search"):
                    solver = {"math": L.solve_math, "data_analysis": L.solve_data,
                              "search": L.solve_search}[ty]
                    r = await solver(self.llm, t, model=MODEL_FAST_ALT)
                    if r and r[0] == "infeasible" and t.raw.get("_llm_infeasible"):
                        self.mark(t, "infeasible_claimed", "two models agree")
                        return
                    if not r or r[0] != "answer":
                        r = await L.agent_solve(self.llm, t, cap=cap)
                else:
                    r = await L.agent_solve(self.llm, t, cap=cap, model=MODEL_FAST_ALT)
            except LLMUnavailable as e:
                log(f"{t.task_id}: LLM unavailable ({e})")
                return
            out = self._consume(t, r, "llm-escalated")
            if out == "infeasible":
                self.mark(t, "infeasible_claimed", "model says infeasible twice")
            elif out != "ok":
                self.mark(t, "failed", t.note or "escalation failed")

        await self.run_queue(pending, escalate, "phase C (escalation)")

    async def phase_verify(self):
        """Second opinion on LLM-derived non-code answers while budget is ample."""
        if not self.llm.enabled or self.ledger.dead:
            return
        cands = [t for t in self.tasks if t.status == "answered_unverified"
                 and t.solver.startswith("llm")
                 and type_of(t) in ("math", "data_analysis", "search")]
        cands.sort(key=lambda t: -t.reward)
        for t in cands:
            if self.ledger.usable() < 0.35 * self.ledger.total or self.time_left() < 120:
                break
            ty = type_of(t)
            solver = {"math": L.solve_math, "data_analysis": L.solve_data,
                      "search": L.solve_search}[ty]
            try:
                r2 = await solver(self.llm, t, model=MODEL_FAST_ALT)
                if r2 and r2[0] == "answer" and r2[1] == t.answer:
                    continue
                r3 = await solver(self.llm, t, model=MODEL_REASON)
            except LLMUnavailable:
                break
            votes = [t.answer, r2[1] if r2 and r2[0] == "answer" else None,
                     r3[1] if r3 and r3[0] == "answer" else None]
            best = max(set(v for v in votes if v), key=votes.count)
            if best != t.answer and votes.count(best) >= 2:
                log(f"{t.task_id}: verification changed {t.answer!r} -> {best!r}")
                self.accept_answer(t, best, t.solver + "+vote", verify="vote")

    async def run(self):
        try:
            self.phase_deterministic()
            log(f"phase A (deterministic) done at {elapsed():.1f}s: "
                f"{sum(t.status in ANSWERED for t in self.tasks)} answered "
                f"({sum(t.status == 'verified' for t in self.tasks)} verified), "
                f"{sum(t.status == 'infeasible_claimed' for t in self.tasks)} infeasible_claimed")
            if self.strategy_name == "legacy":
                await self.phase_llm()
                await self.phase_verify()
            else:
                from .executor import StrategyExecutor
                from .strategies import get as get_strategy
                await StrategyExecutor(self, get_strategy(self.strategy_name),
                                   workers=max(1, min(5, int(os.environ.get("HARNESS_WORKERS", "5"))))).run()
        finally:
            for task in self.tasks:
                if task.status == "pending":
                    task.status, task.note = "skipped", "run ended before completion"
                self.record(task)
            self.summary()

    def summary(self):
        by = {}
        for t in self.tasks:
            by.setdefault(t.status, []).append(t)
        log("=" * 60)
        for k, v in sorted(by.items()):
            log(f"{k:11s} {len(v):3d}  reward {sum(t.reward for t in v):g}")
        log(f"strategy={self.strategy_name}; tokens spent {self.ledger.spent:.0f} / {self.ledger.total:.0f} in "
            f"{self.ledger.calls} calls; backend={self.llm.backend_used}; {elapsed():.0f}s")
        try:
            import json
            trace = os.environ.get("HARNESS_TRACE") or str(
                Path(os.environ.get("TMPDIR", "/tmp"), "harness_trace.json"))
            _atomic_write(Path(trace),
                json.dumps({"strategy": self.strategy_name,
                            "calls": self.ledger.log, "results": self.store.results,
                            "budget": self.ledger.total, "spent": self.ledger.spent,
                            "backend": self.llm.backend_used,
                            "halt_reason": self.ledger.halt_reason,
                            "pending_reservations": self.ledger.pending,
                            "seconds": elapsed()},
                           ensure_ascii=False, indent=1))
            log(f"trace written to {trace}")
        except OSError as error:
            log(f"cannot persist trace: {error}")
            raise
