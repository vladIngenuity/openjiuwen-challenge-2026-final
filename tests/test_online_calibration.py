"""Online calibration must avoid training on unverified text answers."""
import math
import unittest

from harness import strategy as S
from harness.strategies.online_calibration import OnlineCalibration


def task(task_id, ty="coding", p=0.6, cost=200):
    return S.TaskView(task_id, ty, reward=10, check="unittest",
                      est_p=p, est_cost=cost, files_bytes=1500)


def call(cost=100, error=""):
    return S.Call(model="m", transport="raw", input_tokens=100,
                  output_tokens=90, reasoning_tokens=0, cost=cost,
                  sec=1, error=error)


def attempt(task_id, status, cost=100, kind="oneshot", verify="none",
            calls=None):
    return S.AttemptResult(task_id, 1, kind, "m", status, None, verify,
                           cost, 1, calls=tuple(calls if calls is not None
                                               else [call(cost)]))


def state(hist=()):
    return S.RunState(100000, 1000, 80000, 0, 3000,
                      status_by_task={}, history=list(hist))


class OnlineCalibrationTest(unittest.TestCase):
    def setUp(self):
        self.s = OnlineCalibration()

    def test_contract(self):
        self.assertEqual(S.check_strategy(self.s), [])

    def test_cold_start_matches_marginal(self):
        from harness.strategies.marginal_action import MarginalAction
        t = task("coding_99")
        self.assertEqual(self.s.next_action(t, state()),
                         MarginalAction().next_action(t, state()))

    def test_verified_coding_increases_posterior(self):
        t = task("coding_target")
        base, _ = self.s.next_action(t, state())
        h = [attempt("coding_1", S.VERIFIED, verify="unittest") for _ in range(20)]
        got, _ = self.s.next_action(t, state(h))
        self.assertGreater(got, base)
        self.assertLess(got, 1)

    def test_failed_coding_decreases_posterior(self):
        t = task("coding_target")
        base, _ = self.s.next_action(t, state())
        h = [attempt("coding_1", S.FAILED) for _ in range(20)]
        got, _ = self.s.next_action(t, state(h))
        self.assertLess(got, base)
        self.assertGreater(got, 0)

    def test_unverified_text_does_not_train_correctness(self):
        t = task("math_target", "math", p=0.8)
        base, _ = self.s.next_action(t, state())
        h = [attempt("math_1", S.ANSWERED_UNVERIFIED) for _ in range(30)]
        got, _ = self.s.next_action(t, state(h))
        self.assertEqual(got, base)

    def test_failed_api_and_nonmatching_tasks_ignored(self):
        t = task("coding_target")
        baseline = self.s.next_action(t, state())
        h = [attempt("coding_1", S.FAILED, calls=[call(error="HTTP 429")]),
             attempt("unknown_1", S.FAILED),
             attempt("search_1", S.FAILED)]
        self.assertEqual(self.s.next_action(t, state(h)), baseline)

    def test_cost_learns_only_from_valid_completed_requests(self):
        t = task("math_target", "math", cost=500)
        prior_p, prior_c = self.s.next_action(t, state())
        h = [attempt("math_1", S.FAILED, cost=100) for _ in range(15)]
        p, c = self.s.next_action(t, state(h))
        self.assertEqual(p, prior_p)
        self.assertLess(c, prior_c)
        self.assertGreaterEqual(c, 50)

    def test_agent_buckets_separate_from_oneshot(self):
        t = task("coding_target")
        # This task has no history -> its next action is one-shot.
        first = self.s.next_action(t, state())
        h = [attempt("coding_1", S.VERIFIED, kind="agent",
                     verify="unittest") for _ in range(20)]
        self.assertEqual(self.s.next_action(t, state(h)), first)

    def test_all_outputs_finite(self):
        t = task("coding_target")
        p, c = self.s.next_action(t, state(
            [attempt("coding_1", S.FAILED, cost=1e8)]))
        self.assertTrue(math.isfinite(p) and math.isfinite(c))


if __name__ == "__main__":
    unittest.main()
