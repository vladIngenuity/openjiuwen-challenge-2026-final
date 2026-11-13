"""Deterministic contract tests for the opt-in marginal scheduler."""
import unittest

from harness import strategy as S
from harness.strategies.marginal_action import MarginalAction


def task(task_id, reward=1, p=0.8, cost=100):
    return S.TaskView(task_id=task_id, type="math", reward=reward,
                      check="exact_int", est_p=p, est_cost=cost)


def state(statuses, history=()):
    return S.RunState(budget_total=100000, spent=0, remaining=80000,
                      elapsed=0, time_left=2000, status_by_task=statuses,
                      history=list(history))


def failed(task_id, status=S.FAILED):
    return S.AttemptResult(task_id, 1, "oneshot", "m", status, None,
                           "none", 100, 0)


class MarginalActionTests(unittest.TestCase):
    def setUp(self):
        self.s = MarginalAction()

    def test_protocol(self):
        self.assertEqual(S.check_strategy(self.s), [])

    def test_retry_is_discounted(self):
        t = task("t")
        p1, c1 = self.s.next_action(t, state({"t": S.PENDING}))
        p2, c2 = self.s.next_action(t, state({"t": S.PENDING}, [failed("t")]))
        self.assertLess(p2, p1)
        self.assertGreater(c2, c1)

    def test_high_value_retry_can_beat_low_value_first_try(self):
        old = task("high", reward=50)
        new = task("low", reward=1)
        s = state({"high": S.PENDING, "low": S.PENDING}, [failed("high")])
        self.assertEqual(self.s.order([new, old], s)[0], "high")

    def test_claimed_infeasible_is_penalized_more_than_failure(self):
        t = task("t")
        p_fail, _ = self.s.next_action(t, state({"t": S.PENDING}, [failed("t")]))
        p_claim, _ = self.s.next_action(
            t, state({"t": S.PENDING}, [failed("t", S.INFEASIBLE_CLAIMED)]))
        self.assertLess(p_claim, p_fail)

    def test_non_pending_excluded_and_order_deterministic(self):
        a, b = task("a"), task("b")
        s = state({"a": S.VERIFIED, "b": S.PENDING})
        self.assertEqual(self.s.order([a, b], s), ["b"])
        s2 = state({"a": S.PENDING, "b": S.PENDING})
        self.assertEqual(self.s.order([b, a], s2),
                         self.s.order([a, b], s2))


if __name__ == "__main__":
    unittest.main()
