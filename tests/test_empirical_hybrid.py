import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from harness.executor import ONESHOT, StrategyExecutor
from harness.llm import (MODEL_FAST, MODEL_FAST_ALT, MODEL_REASON,
                         MODEL_REASON_ALT)
from harness.strategies import get
from harness.strategy import FAILED, ANSWERED_UNVERIFIED, AttemptResult, Call, RunState, TaskView


def state(**changes):
    values = dict(
        budget_total=100000, spent=0, remaining=98000,
        elapsed=0, time_left=3300,
        status_by_task={}, unavailable_models=(),
    )
    values.update(changes)
    return RunState(**values)


class EmpiricalHybridTests(unittest.TestCase):
    def test_registry_and_bounded_policy(self):
        strategy = get("empirical_hybrid")
        task = TaskView("math_a", "math", 7, "exact_str")
        result = AttemptResult(
            "math_a", 1, "oneshot", MODEL_REASON, FAILED,
            None, "none", 200, 1,
        )
        self.assertFalse(strategy.should_escalate(task, result, state()))
        self.assertFalse(strategy.should_verify(task, result, state()))
        self.assertFalse(strategy.should_diagnose(task, state()))
        self.assertTrue(strategy.endgame_enabled)
        self.assertEqual(strategy.endgame_reserve, 5000)
        self.assertEqual(
            strategy.vote_models, (MODEL_FAST_ALT, MODEL_REASON_ALT)
        )

    def test_category_router_and_model_fallbacks(self):
        strategy = get("empirical_hybrid")
        for task_type in ("math", "coding"):
            task = TaskView(task_type, task_type, 1, "exact_str")
            self.assertEqual(strategy.model_for(task, state(), 1), MODEL_REASON)
            self.assertEqual(
                strategy.model_for(
                    task, state(unavailable_models=(MODEL_REASON,)), 1),
                MODEL_REASON_ALT,
            )
        for task_type in ("search", "data_analysis"):
            task = TaskView(task_type, task_type, 1, "exact_str")
            self.assertEqual(strategy.model_for(task, state(), 1), MODEL_FAST)
            self.assertEqual(
                strategy.model_for(
                    task, state(unavailable_models=(MODEL_FAST,)), 1),
                MODEL_FAST_ALT,
            )

    def test_measured_value_order_and_caps(self):
        strategy = get("empirical_hybrid")
        tasks = [
            TaskView("math", "math", 5, "exact_str"),
            TaskView("search", "search", 5, "exact_str"),
            TaskView("data", "data_analysis", 5, "exact_str"),
            TaskView("coding", "coding", 5, "unittest"),
        ]
        run = state(status_by_task={task.task_id: "pending" for task in tasks})
        self.assertEqual(
            strategy.order(tasks, run),
            ["search", "data", "math", "coding"],
        )
        self.assertEqual(strategy.budget_for(tasks[0], run), 1400)
        self.assertEqual(strategy.budget_for(tasks[1], run), 500)
        self.assertEqual(strategy.budget_for(tasks[2], run), 1300)
        self.assertEqual(strategy.budget_for(tasks[3], run), 1500)

    def test_global_remaining_clamps_reservation(self):
        strategy = get("empirical_hybrid")
        task = TaskView("math", "math", 5, "exact_str")
        self.assertEqual(strategy.budget_for(task, state(remaining=275)), 275)

    def test_endgame_ranks_expected_correction_value_and_excludes_coding(self):
        strategy = get("empirical_hybrid")
        tasks = [
            TaskView("math", "math", 5, "exact_str"),
            TaskView("search", "search", 5, "exact_str"),
            TaskView("data", "data_analysis", 5, "exact_str"),
            TaskView("coding", "coding", 10, "unittest"),
        ]
        self.assertEqual(
            strategy.endgame_order(tasks, state()),
            ["search", "data", "math"],
        )


class EndgameExecutorTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def harness(tasks, usable=5300):
        ledger = SimpleNamespace(
            total=100000.0, spent=94700.0, dead=False, log=[],
            usable=lambda: usable,
        )
        return SimpleNamespace(
            tasks=tasks, ledger=ledger,
            llm=SimpleNamespace(bad_models=set()),
            time_left=lambda: 1000.0,
        )

    @staticmethod
    def task(task_id, task_type, reward, status="answered_unverified"):
        return SimpleNamespace(
            task_id=task_id, task_type=task_type, reward=reward,
            status=status, verify="none", solver="llm-oneshot",
            cost=0.0, answer="A",
        )

    async def test_endgame_waits_until_no_pending_task_remains(self):
        answered = self.task("answered", "search", 5)
        pending = self.task("pending", "math", 9, status="pending")
        executor = StrategyExecutor(
            self.harness([answered, pending]), get("empirical_hybrid")
        )
        executor.view = lambda task: TaskView(
            task.task_id, task.task_type, task.reward, "exact_str"
        )
        called = []

        async def fake_vote(*args, **kwargs):
            called.append(args[0].task_id)

        executor._vote = fake_vote
        await executor._run_endgame()
        self.assertEqual(called, [])

    async def test_endgame_preserves_reserve_and_uses_ranked_order(self):
        math = self.task("math", "math", 10)
        search = self.task("search", "search", 10)
        executor = StrategyExecutor(
            self.harness([math, search]), get("empirical_hybrid")
        )
        executor.view = lambda task: TaskView(
            task.task_id, task.task_type, task.reward, "exact_str"
        )
        executor.history = [
            AttemptResult(task.task_id, 1, "oneshot", MODEL_FAST,
                          "answered_unverified", "A", "none", 100, 1)
            for task in (math, search)
        ]
        called = []

        async def fake_vote(task, view, first, *, cap=None):
            called.append((task.task_id, cap))
            return AttemptResult(
                task.task_id, 1, "vote", MODEL_FAST_ALT,
                "answered_unverified", "A", "vote", 0, 0,
            )

        executor._vote = fake_vote
        await executor._run_endgame()

        self.assertEqual(called, [("search", 300), ("math", 300)])
        self.assertEqual(len(executor.history), 4)

    async def test_surplus_rescues_only_measured_truncation_once(self):
        truncated = self.task("truncated", "math", 5, status=FAILED)
        uncertain = self.task("uncertain", "math", 5, status=FAILED)
        other = self.task("other", "math", 5, status=FAILED)
        for task in (truncated, uncertain, other):
            task.cost = 1300.0
        harness = self.harness([truncated, uncertain, other], usable=10000)
        executor = StrategyExecutor(harness, get("empirical_hybrid"))
        executor.view = lambda task: TaskView(
            task.task_id, task.task_type, task.reward, "exact_str"
        )
        measured = Call("model", "raw", 100, 1290, 0, 1300, 1,
                        "math:truncated", "", "usage", "length")
        ambiguous = Call("model", "raw", 0, 0, 0, 1300, 1,
                         "math:uncertain", "timeout", "uncertain_full_reservation")
        executor.history = [
            AttemptResult("truncated", 1, "oneshot", "model", FAILED, None,
                          "none", 1300, 1, (measured,),
                          "output cap: truncated response"),
            AttemptResult("uncertain", 1, "oneshot", "model", FAILED, None,
                          "none", 1300, 1, (ambiguous,),
                          "output cap: truncated response"),
            AttemptResult("other", 1, "oneshot", "model", FAILED, None,
                          "none", 1300, 1, (measured,), "no result"),
        ]
        called = []

        async def fake_attempt(task, view, attempt, model, cap, *, rescue=False):
            called.append((task.task_id, attempt, model, cap, rescue))
            task.status = ANSWERED_UNVERIFIED
            return AttemptResult(task.task_id, attempt, "rescue", model,
                                 ANSWERED_UNVERIFIED, "42", "none", 100, 1)

        executor._attempt = fake_attempt
        await executor._rescue_truncated(5000, 240)
        self.assertEqual(called, [
            ("truncated", 2, executor.s.endgame_rescue_model, 2400.0, True)
        ])
        await executor._rescue_truncated(5000, 240)
        self.assertEqual(len(called), 1)

    async def test_rescue_requests_larger_complete_answer(self):
        task = self.task("math", "math", 5, status=FAILED)
        task.cost = 1300.0
        harness = self.harness([task], usable=10000)
        harness._calls_for = lambda _: []
        harness.accept_answer = lambda t, answer, solver, verify: setattr(
            t, "status", ANSWERED_UNVERIFIED)
        executor = StrategyExecutor(harness, get("empirical_hybrid"))
        view = TaskView("math", "math", 5, "exact_str")
        solve = AsyncMock(return_value=("answer", "42", "code"))
        with patch.dict(ONESHOT, {"math": solve}):
            result = await executor._attempt(task, view, 2,
                                             executor.s.endgame_rescue_model,
                                             2400, rescue=True)
        self.assertEqual(result.status, ANSWERED_UNVERIFIED)
        self.assertEqual(result.kind, "rescue")
        self.assertEqual(solve.await_args.kwargs["max_tokens"], 1800)
        self.assertEqual(solve.await_args.kwargs["repairs"], 1)
