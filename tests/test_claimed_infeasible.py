"""Opt-in (HARNESS_CLAIMED_TASK_CAP): tasks a model already called INFEASIBLE
escalate only from spare budget, under a lower total ceiling (Baseline)."""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import strategy as S  # noqa: E402
from harness.strategies import baseline as B  # noqa: E402


def view(det=S.DET_NONE, ty="data_analysis"):
    return S.TaskView(task_id="t1", type=ty, reward=5, check="exact", instruction_chars=300,
                      n_files=1, files_bytes=500, det_status=det, det_note="",
                      est_cost=None, est_p=None)


def state(history, remaining=80000.0):
    return S.RunState(budget_total=100000, spent=100000 - remaining, remaining=remaining,
                      elapsed=10, time_left=3000, status_by_task={"t1": S.PENDING},
                      history=tuple(history))


def attempt(n, cost, status=S.FAILED, kind="oneshot"):
    return S.AttemptResult("t1", n, kind, "m", status, None, "none", cost, 1.0)


def claimed(n, cost):
    return attempt(n, cost, S.INFEASIBLE_CLAIMED)


class ClaimedInfeasible(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(B, "CLAIMED_TASK_CAP", 700.0)
        p.start()
        self.addCleanup(p.stop)

    def test_spare_budget_rechecked_when_attempt_is_authorized(self):
        # review of #23: other workers spend the budget between should_escalate
        # (80k left) and budget_for (20k left); the follow-up must not run
        b = B.Baseline()
        h = [claimed(1, 200)]
        self.assertTrue(b.should_escalate(view(), h[-1], state(h, remaining=80000)))
        self.assertLess(b.budget_for(view(), state(h, remaining=20000)), S.MIN_CAP)

    def test_one_claim_with_spare_budget_escalates_under_lower_ceiling(self):
        b = B.Baseline()
        h = [claimed(1, 200)]
        self.assertTrue(b.should_escalate(view(), h[-1], state(h)))
        cap = b.budget_for(view(), state(h))
        self.assertGreaterEqual(cap, B.CLAIMED_MIN_ATTEMPT)
        self.assertLessEqual(cap, B.CLAIMED_TASK_CAP - 200 + 1e-6)

    def test_one_claim_without_spare_budget_stops(self):
        b = B.Baseline()
        h = [claimed(1, 200)]
        low = B.CLAIMED_SPARE_FRAC * 100000
        self.assertFalse(b.should_escalate(view(), h[-1], state(h, remaining=low)))

    def test_claimed_ceiling_used_up_stops(self):
        b = B.Baseline()
        h = [attempt(1, 250), claimed(2, B.CLAIMED_TASK_CAP - 250 - B.CLAIMED_MIN_ATTEMPT + 1)]
        self.assertFalse(b.should_escalate(view(), h[-1], state(h)))

    def test_total_spend_of_claimed_task_bounded(self):
        # walk the escalation chain as the Executor would; each attempt spends its whole cap
        b = B.Baseline()
        h = [claimed(1, 200)]
        while b.should_escalate(view(), h[-1], state(h)):
            cap = b.budget_for(view(), state(h))
            h.append(claimed(len(h) + 1, cap))
        self.assertLessEqual(sum(a.cost for a in h), B.CLAIMED_TASK_CAP + 1e-6)

    def test_unclaimed_failure_keeps_full_ceiling(self):
        b = B.Baseline()
        h = [attempt(1, 200), attempt(2, 300)]
        self.assertTrue(b.should_escalate(view(), h[-1], state(h)))
        self.assertGreater(b.budget_for(view(), state(h)), B.CLAIMED_TASK_CAP)

    def test_contract_still_holds(self):
        self.assertEqual(S.check_strategy(B.Baseline()), [])
        self.assertLess(B.CLAIMED_TASK_CAP, B.TASK_CAP)

    def test_general_task_cap_still_bounds_claimed_tasks(self):
        # #27 x #23: with a general TASK_CAP below the claimed ceiling, the
        # smaller of the two wins
        b = B.Baseline()
        h = [claimed(1, 200)]
        with mock.patch.object(B, "TASK_CAP", 500.0):
            self.assertLessEqual(b.budget_for(view(), state(h)), 500.0 - 200 + 1e-6)


class OffByDefault(unittest.TestCase):
    def test_default_is_off(self):
        self.assertEqual(B.CLAIMED_TASK_CAP, 0.0)

    def test_claimed_task_behaves_as_before_when_off(self):
        b = B.Baseline()
        h = [claimed(1, 200)]
        low = state(h, remaining=20000)
        self.assertTrue(b.should_escalate(view(), h[-1], low))
        self.assertGreater(b.budget_for(view(), low), 700)


if __name__ == "__main__":
    unittest.main()
