"""Offline regression: unknown usage must not train solver success estimates."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from harness.budget import BudgetLedger
from harness.executor import StrategyExecutor
from harness.llm import LLMUnavailable
from harness.pipeline import Harness
from harness.strategies.baseline import Baseline
from harness.strategy import SKIPPED
from harness.tasks import AnswerStore, Task


class ExecutorUnavailableTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def make_executor(tmp):
        task = Task("case", "coding", "synthetic", 1, "unittest", Path(tmp))
        harness = object.__new__(Harness)
        harness.tasks = [task]
        harness.ledger = BudgetLedger(total=10000)
        harness.llm = SimpleNamespace(bad_models=set())
        harness.time_left = lambda: 300
        harness.store = AnswerStore(None)
        strategy = Baseline()
        strategy.observe = Mock()
        strategy.should_escalate = Mock(return_value=False)
        return task, harness, strategy, StrategyExecutor(harness, strategy)

    async def test_uncertain_charge_is_not_a_solver_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            task, harness, strategy, executor = self.make_executor(tmp)

            async def interrupted(*args, **kwargs):
                ticket = harness.ledger.try_reserve(100)
                harness.ledger.commit_uncertain(ticket, {"tag": "code:case", "http_status": 503})
                raise LLMUnavailable("uncertain_usage")

            with patch("harness.executor.L.solve_coding", side_effect=interrupted):
                await executor._process(task)
            self.assertEqual(harness.ledger.spent, 100)
            self.assertTrue(harness.ledger.dead)
            self.assertEqual(task.status, SKIPPED)
            self.assertEqual(executor.history, [])
            self.assertEqual(executor.type_stats.get("coding", {}).get("n", 0), 0)
            strategy.observe.assert_not_called()
            strategy.should_escalate.assert_not_called()
            row = harness.store.results["case"]
            self.assertEqual(row["cost_total"], 100)
            self.assertEqual(row["calls"][0]["accounting"], "uncertain_full_reservation")

    async def test_cap_refusal_before_spending_is_deferred_not_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            task, harness, strategy, executor = self.make_executor(tmp)

            with patch("harness.executor.L.solve_coding",
                       side_effect=LLMUnavailable("cap")):
                await executor._process(task)

            self.assertEqual(task.status, "pending")
            self.assertIn(task.task_id, executor.deferred)
            self.assertEqual(executor.history, [])
            self.assertEqual(executor.type_stats["coding"]["n"], 0)
            self.assertEqual(harness.ledger.spent, 0)
            strategy.observe.assert_not_called()
            strategy.should_escalate.assert_not_called()

    async def test_cap_after_measured_spending_remains_solver_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            task, harness, strategy, executor = self.make_executor(tmp)

            async def exhausted(*args, **kwargs):
                ticket = harness.ledger.try_reserve(100)
                harness.ledger.commit(ticket, 10, 50,
                                      meta={"tag": "code:case", "accounting": "usage"})
                raise LLMUnavailable("cap")

            with patch("harness.executor.L.solve_coding", side_effect=exhausted):
                await executor._process(task)

            self.assertEqual(task.status, "failed")
            self.assertEqual(len(executor.history), 1)
            self.assertEqual(executor.history[0].status, "failed")
            self.assertEqual(executor.type_stats["coding"]["n"], 1)
            self.assertEqual(harness.ledger.spent, 51)
            strategy.observe.assert_called_once()
            strategy.should_escalate.assert_called_once()

    async def test_legacy_unknown_usage_does_not_update_solver_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Task("case", "coding", "synthetic", 1, "unittest", Path(tmp))
            harness = object.__new__(Harness)
            harness.ledger = BudgetLedger(total=10000)
            harness.llm = SimpleNamespace()
            harness.stats = {"coding": {"n": 0, "ok": 0, "cost": 0.0}}

            async def interrupted(*args, **kwargs):
                ticket = harness.ledger.try_reserve(100)
                harness.ledger.commit_uncertain(
                    ticket,
                    {"tag": "code:case", "accounting": "uncertain_full_reservation"},
                )
                raise LLMUnavailable("uncertain_usage")

            with patch("harness.pipeline.L.solve_coding", side_effect=interrupted):
                result = await harness.attempt_cheap(task)

            self.assertEqual(result, "nobudget")
            self.assertEqual(task.cost, 100)
            self.assertEqual(harness.stats["coding"]["n"], 0)
            self.assertEqual(harness.stats["coding"]["cost"], 0)
