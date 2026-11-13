"""Preflight parse, fallback, routing, and ablation invariants."""
import asyncio
import json
import unittest
from types import SimpleNamespace

from harness import strategy as S
from harness.preflight import parse_ratings, preflight_all
from harness.strategies.ablations import (
    MarginalNoPenalty, MarginalSoftPenalty, OnlineCostOnly)
from harness.strategies.baseline import Baseline
from harness.strategies.marginal_action import MarginalAction
from harness.strategies.qwen_preflight import QwenPreflight
from harness.strategies import get


def tv(tid, reward=5, cost=200):
    return S.TaskView(tid, "math", reward, "exact_int",
                      instruction_chars=100, est_cost=cost, est_p=0.8)


def state(diags=None):
    return S.RunState(4800, 0, 4800, 0, 1800,
                      status_by_task={"math_1": S.PENDING,
                                      "math_2": S.PENDING},
                      diagnostics=diags or {})


class PreflightTests(unittest.TestCase):
    def test_registry_and_protocol(self):
        for name in ("qwen_preflight", "marginal_no_penalty",
                     "marginal_soft_penalty", "online_cost_only"):
            self.assertEqual(S.check_strategy(get(name)), [])

    def test_strict_json(self):
        self.assertEqual(parse_ratings("[0,5,10]", 3), [0,5,10])
        self.assertIsNone(parse_ratings("[1,2]", 3))
        self.assertIsNone(parse_ratings("[1.0,2]", 2))
        self.assertIsNone(parse_ratings("[false,2]", 2))
        self.assertIsNone(parse_ratings("[11,2]", 2))

    def test_unavailable_diagnostic_falls_back(self):
        tasks = [tv("math_1"), tv("math_2")]
        self.assertEqual(QwenPreflight().order(tasks, state()),
                         Baseline().order(tasks, state()))

    def test_preflight_changes_ranking_without_skipping(self):
        tasks = [tv("math_1"), tv("math_2")]
        d = {"math_1": {"preflight_score": 0},
             "math_2": {"preflight_score": 10}}
        self.assertEqual(QwenPreflight().order(tasks, state(d)),
                         ["math_2", "math_1"])

    def test_ablation_multiplier_changes_retry_prior(self):
        t = tv("math_1")
        attempt = S.AttemptResult("math_1", 1, "oneshot", "m",
                                  S.FAILED, None, "none", 100, 1)
        st = state()
        st.history = [attempt]
        prior = MarginalAction().next_action(t, st)[0]
        soft = MarginalSoftPenalty().next_action(t, st)[0]
        none = MarginalNoPenalty().next_action(t, st)[0]
        self.assertLess(prior, soft)
        self.assertLess(soft, none)

    def test_cost_only_same_prior_probability(self):
        st = state()
        t = tv("math_1")
        self.assertEqual(OnlineCostOnly().next_action(t, st)[0],
                         MarginalAction().next_action(t, st)[0])

    def test_no_llm_means_no_preflight(self):
        h = SimpleNamespace(llm=SimpleNamespace(enabled=False),
                            tasks=[], time_left=lambda: 1000)
        self.assertEqual(asyncio.run(preflight_all(SimpleNamespace(h=h))), {})


if __name__ == "__main__":
    unittest.main()
