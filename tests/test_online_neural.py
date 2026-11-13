"""Online MLP actually updates trainable weights, and never learns from unverified text."""
import math
import unittest

from harness import strategy as S
from harness.strategies.online_neural import OnlineNeural, TinyMLP


def task(category="coding"):
    return S.TaskView(category + "_0001", category, 5, "unittest",
                      instruction_chars=300, n_files=2, files_bytes=1200)


def state():
    return S.RunState(4800, 0, 4800, 0, 1000,
                      status_by_task={"coding_0001": S.PENDING})


def action(category="coding", status=S.VERIFIED, verify="unittest", cost=180,
           error=""):
    call = S.Call("m", "raw", 400, 140, 0, cost, 1, error=error)
    return S.AttemptResult(category + "_0001", 1, "oneshot", "m",
                           status, None, verify, cost, 1, calls=(call,))


class NeuralOnlineTest(unittest.TestCase):
    def setUp(self):
        self.s = OnlineNeural()

    def test_strategy_contract(self):
        self.assertEqual(S.check_strategy(self.s), [])

    def test_zero_prior_cold_start_and_determinism(self):
        t = task()
        a = self.s._predict(t, state(), 1)
        b = OnlineNeural()._predict(t, state(), 1)
        self.assertEqual(a, b)
        self.assertEqual(a[0], self.s._prior_p(t, state()))

    def test_cost_observation_changes_actual_weights(self):
        t = task("math")
        before = [row[:] for row in self.s.model.w2]
        for _ in range(20):
            self.s.observe(t, action("math", S.ANSWERED_UNVERIFIED,
                                     verify="none", cost=80), state())
        self.assertEqual(self.s.model.cost_samples, 20)
        self.assertEqual(self.s.model.label_samples, 0)
        self.assertNotEqual(before[0], self.s.model.w2[0])
        self.assertEqual(before[1], self.s.model.w2[1])

    def test_public_coding_success_updates_label_head(self):
        t = task()
        original = self.s.model.b2[1]
        for _ in range(25):
            self.s.observe(t, action(), state())
        self.assertEqual(self.s.model.label_samples, 25)
        self.assertGreater(self.s.model.b2[1], original)

    def test_coding_failure_lowers_probability(self):
        t = task()
        initial = self.s._predict(t, state(), 1)[0]
        for _ in range(25):
            self.s.observe(t, action(status=S.FAILED, verify="none"), state())
        self.assertLess(self.s._predict(t, state(), 1)[0], initial)

    def test_unknown_text_correctness_never_updates_label(self):
        t = task("search")
        for _ in range(40):
            self.s.observe(t, action("search", S.ANSWERED_UNVERIFIED,
                                     "vote"), state())
        self.assertEqual(self.s.model.label_samples, 0)

    def test_no_training_on_failed_transport_or_unbilled_action(self):
        t = task()
        self.s.observe(t, action(error="429"), state())
        self.s.observe(t, action(cost=0), state())
        self.assertEqual(self.s.model.cost_samples, 0)
        self.assertEqual(self.s.model.label_samples, 0)

    def test_output_finite_and_clamped_after_repeated_training(self):
        t = task()
        for _ in range(150):
            self.s.observe(t, action(cost=100000), state())
        p, c = self.s._predict(t, state(), 1)
        self.assertTrue(math.isfinite(p) and math.isfinite(c))
        self.assertGreater(c, 0)


if __name__ == "__main__":
    unittest.main()
