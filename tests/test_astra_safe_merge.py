"""Regression checks for selected safe handoff fixes."""
import tempfile
import sys
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from harness.budget import BudgetLedger
from harness.llm import LLM, Usage
from harness import llm_solvers
from harness.tasks import Task, _atomic_write


class SafeMerge(unittest.IsolatedAsyncioTestCase):
    async def test_finish_reason_is_accounted_and_returned(self):
        llm = LLM(BudgetLedger(2000))
        llm.enabled = True
        llm._oj_ok = False
        llm._call_raw = AsyncMock(return_value=(
            "123", [], Usage(100, 3, 0, "length"), ""))
        answer = await llm.chat([])
        self.assertEqual(answer["finish_reason"], "length")
        self.assertEqual(llm.ledger.log[-1]["finish_reason"], "length")
        self.assertEqual(llm.ledger.spent, 13)

    async def test_truncated_answer_is_not_used(self):
        llm = SimpleNamespace(chat=AsyncMock(return_value={
            "content": "123", "tool_calls": [], "cost": 13,
            "finish_reason": "length"}))
        with tempfile.TemporaryDirectory() as directory:
            task = Task("t", "math", "question", 5, "exact_int", Path(directory))
            with patch.object(llm_solvers.sandbox, "run_python",
                              side_effect=AssertionError("must not execute")):
                result = await llm_solvers._code_answer(
                    llm, task, "question", task.ws, "model", 350, "math:t")
            self.assertEqual(result[0], "error")
            self.assertEqual(task.cost, 13)

    async def test_ambiguous_error_still_halts_without_retry(self):
        llm = LLM(BudgetLedger(2000))
        llm.enabled = True
        llm._oj_ok = False
        llm._call_raw = AsyncMock(side_effect=TimeoutError("connection lost"))
        with self.assertRaises(Exception):
            await llm.chat([])
        self.assertEqual(llm._call_raw.await_count, 1)
        self.assertTrue(llm.ledger.dead)

    async def test_sdk_tool_dict_arguments_become_json(self):
        llm = LLM(BudgetLedger(2000))
        response = SimpleNamespace(
            tool_calls=[SimpleNamespace(id="c1", name="submit",
                                        arguments={"answer": "42"})],
            content="", usage_metadata=SimpleNamespace(
                input_tokens=100, output_tokens=10, reasoning_tokens=0),
            reasoning_content="", finish_reason="tool_calls")
        llm._oj_model = lambda model: SimpleNamespace(
            invoke=AsyncMock(return_value=response))
        _, calls, usage, _ = await llm._call_oj("model", [], 100, [])
        self.assertEqual(json.loads(calls[0]["arguments"]), {"answer": "42"})
        self.assertEqual(usage.finish_reason, "tool_calls")

    def test_atomic_answer_is_fsynced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answer.txt"
            with patch("harness.tasks.os.fsync", wraps=__import__("os").fsync) as fsync:
                _atomic_write(path, "42\n")
            self.assertEqual(path.read_text(), "42\n")
            fsync.assert_called_once()

    def test_partial_sdk_schema_failure_restarts_plain_schema_list(self):
        def first(path: str):
            return path

        def second(answer: str):
            return answer

        info = SimpleNamespace(description="first", parameters={"type": "object"})
        wrapped = SimpleNamespace(card=SimpleNamespace(tool_info=lambda: info))
        factory = unittest.mock.Mock(side_effect=[wrapped, RuntimeError("SDK mismatch")])
        with patch.dict(sys.modules, {
            "openjiuwen.core.foundation.tool": SimpleNamespace(tool=factory)
        }):
            schemas, wrappers = llm_solvers._schemas({
                "first": first, "second": second})
        self.assertEqual([item["name"] for item in schemas], ["first", "second"])
        self.assertEqual(wrappers, {})
