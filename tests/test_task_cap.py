"""One task may not consume more than TASK_CAP units in total (Baseline)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import strategy as S  # noqa: E402
from harness.strategies import baseline as B  # noqa: E402


def view(tid="t1", ty="data_analysis"):
    return S.TaskView(task_id=tid, type=ty, reward=5, check="exact", instruction_chars=300,
                      n_files=1, files_bytes=500, det_status=S.DET_NONE, det_note="",
                      est_cost=None, est_p=None)


def state(history, remaining=80000.0):
    return S.RunState(budget_total=100000, spent=100000 - remaining, remaining=remaining,
                      elapsed=10, time_left=3000, status_by_task={"t1": S.PENDING},
                      history=tuple(history))


def attempt(n, cost, status=S.FAILED, kind="oneshot"):
    return S.AttemptResult("t1", n, kind, "m", status, None, "none", cost, 1.0)


class TaskCap(unittest.TestCase):
    def test_escalation_is_capped_by_what_the_task_already_spent(self):
        b = B.Baseline()
        cap = b.budget_for(view(), state([attempt(1, 300), attempt(2, 400)]))
        self.assertLessEqual(cap, B.TASK_CAP - 700 + 1e-6)
        self.assertLessEqual(cap, B.AGENT_CAP)

    def test_no_escalation_once_the_cap_is_used_up(self):
        b = B.Baseline()
        h = [attempt(1, 600), attempt(2, B.TASK_CAP - 600)]
        self.assertFalse(b.should_escalate(view(), h[-1], state(h)))
        self.assertLess(b.budget_for(view(), state(h)), S.MIN_CAP)

    def test_normal_escalation_still_allowed(self):
        b = B.Baseline()
        h = [attempt(1, 200)]
        self.assertTrue(b.should_escalate(view(), h[-1], state(h)))
        self.assertGreaterEqual(b.budget_for(view(), state(h)), 800)

    def test_contract_still_holds(self):
        self.assertEqual(S.check_strategy(B.Baseline()), [])
        self.assertLessEqual(B.Baseline.vote_cap, B.TASK_CAP)


if __name__ == "__main__":
    unittest.main()
