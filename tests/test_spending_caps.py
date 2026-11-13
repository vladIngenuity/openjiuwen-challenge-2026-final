"""Spending caps and deferral (contract v1.0, docs/contracts/strategy.md).

Uses a fake transport, no network: checks that
* every LLM call inside cap_scope is clamped so the scope cannot exceed its cap;
* a scope that has no room left refuses the call before spending;
* the global ledger still refuses calls a scope would allow;
* a deferred task is offered again only after another attempt finishes.
"""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import strategy as S  # noqa: E402
from harness.budget import BudgetLedger  # noqa: E402
from harness.llm import LLM, LLMUnavailable, cap_scope  # noqa: E402

MODEL = "qwen3.8-27b-noreason"


class FakeLLM:
    """Wraps a real LLM object but replaces the network with a stub that
    returns exactly max_tokens of output (the worst case)."""

    def __init__(self, total=100000.0):
        self.ledger = BudgetLedger(total=total)
        self.llm = make_llm(self.ledger)
        self.seen_max_tokens = []

        async def raw(model, messages, max_tokens, tools):
            self.seen_max_tokens.append(max_tokens)
            return ("ok", [], (10, max_tokens, 0), "")
        self.llm._oj_ok = False
        self.llm._call_raw = raw


def make_llm(ledger):
    import os
    os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    os.environ.setdefault("LLM_API_KEY", "x")
    llm = LLM(ledger)
    llm.enabled = True
    return llm


def chat(f, max_tokens=900):
    return asyncio.run(f.llm.chat([{"role": "user", "content": "hi"}], model=MODEL,
                                  max_tokens=max_tokens, tag="t:x"))


class CapScopeTest(unittest.TestCase):
    def test_calls_are_clamped_to_scope(self):
        f = FakeLLM()

        async def run():
            spent = 0.0
            with cap_scope(1000) as sc:
                for _ in range(5):
                    try:
                        r = await f.llm.chat([{"role": "user", "content": "hi"}], model=MODEL,
                                             max_tokens=900, tag="t:x")
                        spent += r["cost"]
                    except LLMUnavailable as e:
                        self.assertEqual(str(e), "cap")
                        break
                return spent, sc["spent"]
        spent, sc_spent = asyncio.run(run())
        self.assertAlmostEqual(spent, sc_spent)
        # Stub usage is below the reserved input bound.
        self.assertLessEqual(spent, 1000)
        self.assertEqual(f.seen_max_tokens[0], 900)
        self.assertLess(f.seen_max_tokens[1], 900)

    def test_no_room_refuses_before_spending(self):
        f = FakeLLM()

        async def run():
            with cap_scope(10):
                await f.llm.chat([{"role": "user", "content": "hi"}], model=MODEL,
                                 max_tokens=900, tag="t:x")
        with self.assertRaises(LLMUnavailable) as cm:
            asyncio.run(run())
        self.assertEqual(str(cm.exception), "cap")
        self.assertEqual(f.ledger.spent, 0)
        self.assertEqual(f.seen_max_tokens, [])

    def test_global_ledger_still_wins(self):
        f = FakeLLM(total=1000)        # usable = 1000 - 300 reserve = 700

        async def run():
            with cap_scope(5000):
                await f.llm.chat([{"role": "user", "content": "hi"}], model=MODEL,
                                 max_tokens=900, tag="t:x")
        with self.assertRaises(LLMUnavailable) as cm:
            asyncio.run(run())
        self.assertEqual(str(cm.exception), "budget")
        self.assertEqual(f.ledger.spent, 0)

    def test_without_scope_no_clamp(self):
        f = FakeLLM()
        chat(f, 900)
        self.assertEqual(f.seen_max_tokens, [900])


class DeferralTest(unittest.TestCase):
    def test_deferred_task_returns_after_next_attempt(self):
        from harness.executor import StrategyExecutor
        ex = StrategyExecutor.__new__(StrategyExecutor)
        ex.history, ex.deferred = [], {}
        ex._defer("a", "test")
        self.assertFalse(ex._eligible("a"))
        self.assertTrue(ex._eligible("b"))
        ex.history.append(S.AttemptResult("b", 1, "oneshot", MODEL, S.FAILED, None, "none", 10, 1))
        self.assertTrue(ex._eligible("a"))

    def test_contract_constants(self):
        self.assertGreater(S.DIAG_CAP, 0)
        self.assertGreaterEqual(S.VOTE_CAP_DEFAULT, S.MIN_CAP)
        st = S.RunState(budget_total=1, spent=0, remaining=1, elapsed=0, time_left=1)
        self.assertEqual(st.deferred, ())
        self.assertEqual(st.in_flight, ())


if __name__ == "__main__":
    unittest.main()
