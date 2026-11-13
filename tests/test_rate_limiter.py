"""One global pace for physical LLM calls, without changing accounting."""
import asyncio
import os
import time
import unittest
from unittest.mock import patch

from harness.budget import BudgetLedger
from harness.llm import (LLM, LLMUnavailable, MODEL_FAST, MODEL_FAST_ALT,
                         ProxyError, RateLimiter, Usage)


class RateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_is_one_in_flight_and_thirty_rpm(self):
        with patch.dict(os.environ, {}, clear=True):
            llm = LLM(BudgetLedger(10000))
        self.assertEqual(llm.rate_limiter.interval, 2.0)
        self.assertEqual(llm.sem._value, 1)

    async def test_concurrent_models_share_one_start_interval(self):
        llm = LLM(BudgetLedger(10000), max_concurrency=3)
        llm.enabled = True
        llm._oj_ok = False
        llm.rate_limiter = RateLimiter(1200)  # 50 ms, fast offline test
        starts = []

        async def physical_call(model, messages, output, tools):
            starts.append((model, time.monotonic()))
            return "42", [], Usage(100, 10, 0), ""

        llm._call_raw = physical_call
        await asyncio.gather(
            llm.chat([], model=MODEL_FAST),
            llm.chat([], model=MODEL_FAST_ALT),
            llm.chat([], model=MODEL_FAST))
        self.assertEqual(len(starts), 3)
        self.assertGreaterEqual(min(starts[i+1][1] - starts[i][1]
                                    for i in range(2)), 0.045)
        self.assertEqual(llm.ledger.calls, 3)
        self.assertEqual(llm.ledger.pending, 0)

    async def test_cancelled_waiter_has_no_reservation_or_dispatch(self):
        llm = LLM(BudgetLedger(10000))
        llm.enabled = True
        llm._oj_ok = False
        llm.rate_limiter.next_request = time.monotonic() + 60
        called = 0

        async def physical_call(*args):
            nonlocal called
            called += 1
            return "42", [], Usage(100, 10, 0), ""

        llm._call_raw = physical_call
        waiter = asyncio.create_task(llm.chat([]))
        await asyncio.sleep(0.01)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        self.assertEqual(called, 0)
        self.assertEqual(llm.ledger.pending, 0)
        self.assertEqual(llm.ledger.calls, 0)

    async def test_deadline_before_next_slot_has_no_charge(self):
        llm = LLM(BudgetLedger(10000), time_left=lambda: 0.01)
        llm.enabled = True
        llm._oj_ok = False
        llm.rate_limiter.next_request = time.monotonic() + 1
        with self.assertRaisesRegex(LLMUnavailable, "deadline"):
            await llm.chat([])
        self.assertEqual(llm.ledger.calls, 0)
        self.assertEqual(llm.ledger.pending, 0)

    async def test_429_is_still_charged_and_not_retried(self):
        llm = LLM(BudgetLedger(10000))
        llm.enabled = True
        llm._oj_ok = False
        called = 0

        async def physical_call(*args):
            nonlocal called
            called += 1
            raise ProxyError(429, '{"error":{"message":"rate limit"}}')

        llm._call_raw = physical_call
        with self.assertRaises(LLMUnavailable):
            await llm.chat([])
        self.assertEqual(called, 1)
        self.assertTrue(llm.ledger.dead)
        self.assertEqual(llm.ledger.calls, 1)
        self.assertEqual(llm.ledger.pending, 0)
