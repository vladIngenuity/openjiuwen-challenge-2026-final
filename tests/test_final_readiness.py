import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from harness.budget import BudgetLedger, cost_of
from harness.llm import LLM, LLMUnavailable
from harness.llm_solvers import normalize
from harness.pipeline import Harness
from harness.sandbox import run_python, run_suite, scratch_copy
from harness.solvers.math_solver import solve
from harness.solvers.search_solver import retrieve_context
from harness.tasks import AnswerStore, Task
from tools.evaluate import score


class SolverRegressions(unittest.TestCase):
    def test_math_requires_a_final_inventory_question(self):
        question = "A bus holds 32 passengers. How many buses are needed for 141 people?"
        self.assertIsNone(solve(question))
        self.assertEqual(solve("A warehouse starts with 22 boxes. It ships 4 boxes. "
                               "How many boxes does it have at the end?")[0], "18")

    def test_search_includes_structured_inputs_and_respects_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kb = root / "kb"
            kb.mkdir()
            (kb / "register.csv").write_text("device,location\nA1,North\n")
            (kb / "notes.json").write_text('{"status": "confirmed"}')
            (root / "task.json").write_text('{"expected":"keep-private"}')
            context = retrieve_context("Find device A1", root)
            self.assertIn("kb/register.csv", context)
            self.assertIn("A1,North", context)
            self.assertIn("kb/notes.json", context)
            self.assertNotIn("keep-private", context)
            self.assertLessEqual(len(retrieve_context("A1", root, limit_chars=30)), 30)

    def test_answer_normalization_is_exact(self):
        self.assertEqual(normalize("9007199254740993", "exact_int"), "9007199254740993")
        self.assertIsNone(normalize("12,34", "exact_int"))
        self.assertEqual(normalize("X.", "exact_str"), "X.")

    def test_answer_is_written_at_task_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "workspace").mkdir()
            task = Task("math_1", "math", "", 1, "exact_int", root)
            AnswerStore(None).write_answer(task, "0")
            self.assertEqual((root / "answer.txt").read_text(), "0\n")
            self.assertFalse((root / "workspace" / "answer.txt").exists())


class TransportAccounting(unittest.IsolatedAsyncioTestCase):
    def make_llm(self):
        llm = LLM(BudgetLedger(5000))
        llm.enabled = True
        llm._oj_ok = False
        return llm

    async def test_rate_limit_without_usage_is_not_retried(self):
        class RateLimited(Exception):
            status_code = 429
        llm = self.make_llm()
        llm._call_raw = AsyncMock(side_effect=[RateLimited(), ("ok", [], (10, 20, 0), "")])
        with patch("harness.llm.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(LLMUnavailable):
                await llm.chat([{"role": "user", "content": "test"}], tag="math:a")
        sleep.assert_not_awaited()
        self.assertEqual(llm._call_raw.await_count, 1)
        self.assertEqual(llm.ledger.calls, 1)
        self.assertEqual(llm.ledger.log[0]["accounting"], "uncertain_full_reservation")
        self.assertAlmostEqual(llm.ledger.pending, 0)

    async def test_cancellation_charges_in_flight_and_leaves_queued_call_uncharged(self):
        llm = self.make_llm()
        llm.sem = asyncio.Semaphore(1)
        entered = asyncio.Event()

        async def transport(*args):
            entered.set()
            await asyncio.Future()

        llm._call_raw = transport
        running = asyncio.create_task(llm.chat([], max_tokens=80))
        await asyncio.wait_for(entered.wait(), timeout=1)
        queued = asyncio.create_task(llm.chat([], max_tokens=80))
        await asyncio.sleep(0)
        queued.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await queued
        running.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await running
        self.assertEqual(llm.ledger.calls, 1)
        self.assertEqual(llm.ledger.log[0]["error"], "cancelled")
        self.assertEqual(llm.ledger.pending, 0)

    async def test_unknown_usage_stops_new_requests(self):
        llm = self.make_llm()
        llm._call_raw = AsyncMock(return_value=("ok", [], None, ""))
        with self.assertRaises(LLMUnavailable):
            await llm.chat([], max_tokens=80)
        self.assertEqual(llm.ledger.log[0]["accounting"], "uncertain_full_reservation")
        self.assertTrue(llm.ledger.dead)
        self.assertEqual(llm.ledger.pending, 0)
        with self.assertRaises(LLMUnavailable):
            await llm.chat([], max_tokens=80)

    def test_reasoning_accounting_uses_explicit_proxy_contract(self):
        self.assertEqual(cost_of(100, 80, 30), 90)
        self.assertEqual(cost_of(100, 80, 30, reasoning_in_output=False), 120)


@unittest.skipUnless(sys.platform == "linux", "requires Linux workspace isolation")
class CodingRegressions(unittest.TestCase):
    def test_workspace_process_cannot_read_neighbor_or_open_socket(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "work").mkdir()
            (root / "neighbor.txt").write_text("private")
            code = """
import os, socket
assert "LLM_API_KEY" not in os.environ
for probe in (lambda: open("../neighbor.txt"), lambda: open(f"/proc/{os.getppid()}/environ"), socket.socket):
    try:
        probe()
    except PermissionError:
        pass
    else:
        raise AssertionError("workspace isolation failed")
print("isolated")
"""
            with patch.dict(os.environ, {"LLM_API_KEY": "fixture-key"}):
                rc, out = run_python(code, root / "work")
            self.assertEqual(rc, 0, out)
            self.assertEqual(out, "isolated")
            self.assertEqual((root / "neighbor.txt").read_text(), "private")

    def test_scratch_excludes_task_metadata_and_answers(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as temp:
            work = Path(directory)
            (work / "task.json").write_text('{"expected":"secret"}')
            (work / "answer.txt").write_text("old")
            (work / "data.csv").write_text("id\n1\n")
            with patch("harness.sandbox.tempfile.tempdir", temp):
                staged = scratch_copy(work)
            self.assertEqual({p.name for p in staged.iterdir()}, {"data.csv"})

    def test_full_workspace_is_graded_without_marker_and_empty_suite_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = root / "tasks"
            workspace = tasks / "coding_1" / "workspace"
            (workspace / "pkg").mkdir(parents=True)
            (workspace / "pkg" / "util.py").write_text("VALUE = 42\n")
            (workspace / "mylib.py").write_text("from pkg.util import VALUE\n")
            hidden = ("import unittest\nfrom mylib import VALUE\n"
                      "class Test(unittest.TestCase):\n"
                      "    def test_value(self): self.assertEqual(VALUE, 42)\n")
            truth = {"coding_1": {"type": "coding", "reward": 1, "feasible": True, "_hidden": hidden}}
            path = root / "truth.json"
            path.write_text(json.dumps(truth))
            self.assertEqual(score(tasks, path)["score"], 1)
            (workspace / "pkg" / "util.py").write_text("VALUE = 9\n")
            self.assertEqual(score(tasks, path)["score"], 0)
            truth["coding_1"]["_hidden"] = "pass\n"
            path.write_text(json.dumps(truth))
            (workspace.parent / "answer.txt").write_text("DONE\n")
            self.assertEqual(score(tasks, path)["score"], 0)

    def test_failed_multi_file_candidate_leaves_live_workspace_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task_dir = root / "coding_1"
            workspace = task_dir / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "a.py").write_text("A = 1\n")
            (workspace / "b.py").write_text("B = 2\n")
            test = workspace / "test_ab.py"
            test.write_text("import unittest\nfrom a import A\nfrom b import B\n"
                            "class Test(unittest.TestCase):\n"
                            "    def test_both(self): self.assertEqual((A, B), (3, 4))\n")
            task = Task("coding_1", "coding", "Fix a.py and edit b.py. Run python3 test_ab.py.",
                        1, "unittest", task_dir)
            harness = Harness(root, None)
            self.assertFalse(harness.accept_code(task, {"a.py": "A = 3", "b.py": "B = 5"}, "test"))
            self.assertEqual((workspace / "a.py").read_text(), "A = 1\n")
            self.assertEqual((workspace / "b.py").read_text(), "B = 2\n")
            self.assertTrue(harness.accept_code(task, {"a.py": "A = 3", "b.py": "B = 4"}, "test"))
            self.assertTrue(run_suite(workspace, test)[0])
            self.assertEqual((task_dir / "answer.txt").read_text(), "DONE\n")


if __name__ == "__main__":
    unittest.main()
