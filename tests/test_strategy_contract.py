"""Contract tests for harness/strategy.py (run: python -m unittest discover tests)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import strategy as S  # noqa: E402


class Dummy:
    name = "dummy"

    def order(self, tasks, state):
        return [t.task_id for t in tasks if state.status_by_task.get(t.task_id, S.PENDING) == S.PENDING]

    def budget_for(self, task, state):
        return min(500.0, state.remaining)

    def model_for(self, task, state, attempt):
        return "qwen3.8-27b-noreason"

    def should_escalate(self, task, result, state):
        return False

    def should_verify(self, task, result, state):
        return False

    def should_diagnose(self, task, state):
        return False


class ContractTest(unittest.TestCase):
    def test_dummy_satisfies_protocol(self):
        d = Dummy()
        self.assertIsInstance(d, S.Strategy)
        self.assertEqual(S.check_strategy(d), [])

    def test_missing_method_reported(self):
        class Bad:
            name = "bad"

            def order(self, tasks, state):
                return []
        problems = S.check_strategy(Bad())
        self.assertTrue(any("budget_for" in p for p in problems))

    def test_state_history_and_order(self):
        tv = [S.TaskView("a", "math", 5, "exact_int"), S.TaskView("b", "coding", 3, "unittest")]
        st = S.RunState(budget_total=1000, spent=0, remaining=980, elapsed=0, time_left=3000,
                        status_by_task={"a": S.VERIFIED, "b": S.PENDING})
        st.history.append(S.AttemptResult("a", 1, "oneshot", "m", S.VERIFIED, "1", "unittest",
                                          12.5, 1.0))
        self.assertEqual(Dummy().order(tv, st), ["b"])
        self.assertEqual(len(st.attempts("a")), 1)
        self.assertEqual(st.attempts("b"), [])

    def test_taskview_is_frozen_and_has_no_expected(self):
        tv = S.TaskView("a", "math", 1, "exact_int")
        with self.assertRaises(Exception):
            tv.reward = 2  # type: ignore[misc]
        self.assertNotIn("expected", S.TaskView.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
