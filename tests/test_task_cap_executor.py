"""Regression tests for the aggregate per-task budget and configurable caps."""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import strategy as S
from harness.executor import StrategyExecutor
from harness.strategies.baseline import Baseline
from harness.task_limits import TASK_CAP


def view():
    return S.TaskView(task_id="t1", type="coding", reward=12, check="unittest",
                      files_bytes=10000, instruction_chars=500)


def state():
    return S.RunState(budget_total=100000, spent=0, remaining=80000,
                      elapsed=0, time_left=3000,
                      status_by_task={"t1": S.PENDING})


class TestTaskCap(unittest.TestCase):
    def test_first_coding_attempt_is_capped(self):
        self.assertLessEqual(Baseline().budget_for(view(), state()), TASK_CAP)

    def test_explicit_small_agent_cap_not_overridden_by_minimum(self):
        env = dict(os.environ, HARNESS_AGENT_CAP="400")
        script = """
from harness.strategies.baseline import Baseline
from harness.strategy import RunState, TaskView, AttemptResult, FAILED, PENDING
task = TaskView(task_id='t1', type='search', reward=5, check='exact_str')
a = AttemptResult('t1', 1, 'oneshot', 'm', FAILED, None, 'none', 100, 0)
st = RunState(100000, 1000, 80000, 0, 3000, status_by_task={'t1': PENDING}, history=[a])
print(Baseline().budget_for(task, st))
"""
        cp = subprocess.run([sys.executable, "-c", script],
                            capture_output=True, text=True, check=True, env=env)
        self.assertLessEqual(float(cp.stdout.strip()), 400)

    def test_executor_clamps_first_attempt_even_if_strategy_overallocates(self):
        class Strategy(Baseline):
            def budget_for(self, task, st):
                return 10000.0

        t = SimpleNamespace(task_id="t1", cost=0.0)
        h = SimpleNamespace(
            ledger=SimpleNamespace(usable=lambda: 80000.0),
        )
        ex = StrategyExecutor(h, Strategy())
        ex.view = lambda task: view()
        ex.state = state
        seen = []

        async def fake_attempt(task, task_view, n, model, cap):
            seen.append(cap)
            return S.AttemptResult("t1", 1, "oneshot", model,
                                   S.SKIPPED, None, "none", 0, 0,
                                   note="stub")

        ex._attempt = fake_attempt
        asyncio.run(ex._process(t))
        self.assertEqual(len(seen), 1)
        self.assertLessEqual(seen[0], TASK_CAP)

    def test_vote_uses_only_remaining_task_allowance(self):
        t = SimpleNamespace(task_id="t1", answer="A", cost=TASK_CAP - 60,
                            status=S.ANSWERED_UNVERIFIED, verify="none",
                            solver="test")
        h = SimpleNamespace(
            ledger=SimpleNamespace(usable=lambda: 80000.0, log=[]),
            llm=object(),
            _calls_for=lambda t: None,
            record=lambda t: None,
            accept_answer=lambda *args, **kwargs: None,
        )
        ex = StrategyExecutor(h, Baseline())
        first = S.AttemptResult("t1", 1, "oneshot", "m",
                                S.ANSWERED_UNVERIFIED, "A", "none", 50, 0)
        from harness import llm as llm_module

        async def fake_solver(llm, task, model):
            scope = llm_module._SCOPE.get()
            self.assertLessEqual(scope["cap"], 60 + 1e-6)
            task.cost += 40
            return ("answer", "A", "")

        with patch("harness.executor.ONESHOT", {"search": fake_solver}):
            result = asyncio.run(ex._vote(t,
                S.TaskView(task_id="t1", type="search", reward=5, check="exact_str"), first))
        self.assertIsNotNone(result)
        self.assertLessEqual(t.cost, TASK_CAP)

    def test_vote_skips_when_task_allowance_too_small(self):
        t = SimpleNamespace(cost=TASK_CAP - 20)
        h = SimpleNamespace(ledger=SimpleNamespace(usable=lambda: 80000.0))
        ex = StrategyExecutor(h, Baseline())
        result = asyncio.run(ex._vote(t,
            S.TaskView(task_id="t1", type="search", reward=5, check="exact_str"), None))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
