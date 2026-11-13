import os
import unittest
from unittest.mock import patch

from harness import strategy as S
from harness.strategies.random_baseline import RandomBaseline
from harness.strategies.baseline import Baseline


class RandomBaselineTest(unittest.TestCase):
    def setUp(self):
        self.s = RandomBaseline()
        self.tasks = [S.TaskView(f"math_{i:04d}", "math", i+1,
                                 "exact_int") for i in range(30)]
        self.state = S.RunState(10000, 0, 10000, 0, 3000,
                                status_by_task={t.task_id: S.PENDING
                                                for t in self.tasks})

    def test_contract(self):
        self.assertEqual(S.check_strategy(self.s), [])

    def test_deterministic_for_seed_and_input_order(self):
        with patch.dict(os.environ, {"HARNESS_RANDOM_SEED": "71"}):
            a = self.s.order(self.tasks, self.state)
            b = self.s.order(list(reversed(self.tasks)), self.state)
            self.assertEqual(a, b)

    def test_changes_with_seed(self):
        with patch.dict(os.environ, {"HARNESS_RANDOM_SEED": "71"}):
            a = self.s.order(self.tasks, self.state)
        with patch.dict(os.environ, {"HARNESS_RANDOM_SEED": "72"}):
            b = self.s.order(self.tasks, self.state)
        self.assertNotEqual(a, b)

    def test_not_reward_sorted(self):
        with patch.dict(os.environ, {"HARNESS_RANDOM_SEED": "71"}):
            a = self.s.order(self.tasks, self.state)
        self.assertNotEqual(a, Baseline().order(self.tasks, self.state))

    def test_inherits_same_budget_and_model_rules(self):
        t = self.tasks[0]
        self.assertEqual(self.s.budget_for(t, self.state),
                         Baseline().budget_for(t, self.state))
        self.assertEqual(self.s.model_for(t, self.state, 1),
                         Baseline().model_for(t, self.state, 1))

    def test_completed_tasks_removed(self):
        self.state.status_by_task[self.tasks[0].task_id] = S.VERIFIED
        self.assertNotIn(self.tasks[0].task_id,
                         self.s.order(self.tasks, self.state))


if __name__ == "__main__":
    unittest.main()
