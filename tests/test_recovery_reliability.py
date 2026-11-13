import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from harness.budget import BudgetLedger
from harness.llm import LLM, LLMUnavailable, ProxyError, cap_scope, _SetupError
from harness.pipeline import Harness
from harness.tasks import AnswerStore, Task
from harness.solvers.coding_solver import locate
from harness.sandbox import run_suite
from harness import llm_solvers

class Gateway(unittest.IsolatedAsyncioTestCase):
    def llm(self):
        llm = LLM(BudgetLedger(10000))
        llm.enabled, llm._oj_ok = True, False
        return llm

    async def test_503_is_one_send_no_sleep_or_fallback(self):
        llm = self.llm()
        llm._call_raw = AsyncMock(side_effect=ProxyError(503, '{}'))
        with patch('harness.llm.asyncio.sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaisesRegex(LLMUnavailable, 'uncertain_usage'):
                await llm.chat([], tag='math:a')
        sleep.assert_not_awaited()
        self.assertEqual(llm._call_raw.await_count, 1)
        self.assertEqual(llm.ledger.calls, 1)
        self.assertEqual(llm.ledger.pending, 0)
        self.assertIsNone(llm.ledger.log[0]['in'])

    async def test_missing_usage_is_not_fabricated(self):
        llm = self.llm()
        llm._call_raw = AsyncMock(return_value=('answer', [], None, ''))
        with self.assertRaises(LLMUnavailable): await llm.chat([])
        self.assertEqual(llm.ledger.log[0]['accounting'], 'uncertain_full_reservation')
        self.assertIsNone(llm.ledger.log[0]['out'])

    async def test_only_setup_failure_allows_raw(self):
        llm = self.llm(); llm._oj_ok = True
        llm._call_oj = AsyncMock(side_effect=_SetupError())
        llm._call_raw = AsyncMock(return_value=('ok', [], (10, 20, 0), ''))
        await llm.chat([])
        self.assertEqual(llm.ledger.calls, 1)
        self.assertEqual(llm.ledger.pending, 0)
        llm = self.llm(); llm._oj_ok = True
        llm._call_oj = AsyncMock(side_effect=TimeoutError())
        llm._call_raw = AsyncMock()
        with self.assertRaises(LLMUnavailable): await llm.chat([])
        llm._call_raw.assert_not_awaited()

    async def test_nested_scope_cannot_bypass_parent(self):
        llm = self.llm()
        llm._call_raw = AsyncMock(return_value=('ok', [], (10, 50, 0), ''))
        with cap_scope(70) as outer:
            with cap_scope(1000): await llm.chat([], max_tokens=50)
            with cap_scope(1000):
                with self.assertRaisesRegex(LLMUnavailable, 'cap'): await llm.chat([])
            self.assertEqual(outer['spent'], 51)
            self.assertEqual(outer['pending'], 0)

    async def test_journal_written_before_dispatch_and_settlement(self):
        llm = self.llm()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'nested/events.jsonl'
            async def raw(*args):
                self.assertEqual(json.loads(path.read_text())['event'], 'dispatch')
                return ('ok', [], (10, 20, 0), '')
            llm._call_raw = raw
            with patch.dict(os.environ, {'HARNESS_REQUEST_JOURNAL': str(path)}): await llm.chat([])
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([r['event'] for r in records], ['dispatch','settled'])
            self.assertEqual(records[0]['request_id'], records[1]['request_id'])

class Persistence(unittest.IsolatedAsyncioTestCase):
    async def test_crash_still_writes_results_and_atomic_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); task=root/'math_a'; task.mkdir()
            (task/'task.json').write_text(json.dumps({'task_type':'math','instruction':'unknown'}))
            with patch.dict(os.environ, {'HARNESS_TRACE':str(root/'nested/trace.json')}):
                h=Harness(root, str(root/'results.json'))
                with patch.object(h,'phase_deterministic',side_effect=RuntimeError('fixture')):
                    with self.assertRaises(RuntimeError): await h.run()
            tr=json.loads((root/'nested/trace.json').read_text())
            self.assertEqual(tr['results']['math_a']['status'],'skipped')
            self.assertEqual(len(json.loads((root/'results.json').read_text())['results']),1)

    def test_store_write_failure_is_reported_and_can_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); store=AnswerStore(str(root/'results.json'))
            task=Task('a','math','',1,'',root)
            with patch('harness.tasks._atomic_write',side_effect=OSError('fixture')):
                with self.assertRaises(OSError): store.record(task)
            self.assertIsNotNone(store.out_path)
            store.record(task)
            self.assertTrue(store.out_path.is_file())

class PackageCoding(unittest.IsolatedAsyncioTestCase):
    async def test_package_repair_executes_discovered_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'src').mkdir(); (root/'tests').mkdir()
            (root/'src/__init__.py').write_text('')
            (root/'src/core.py').write_text('def f(x): return x-1\n')
            (root/'src/api.py').write_text('from .core import f\n')
            (root/'tests/test_api.py').write_text('import unittest\nfrom src.api import f\nclass Test(unittest.TestCase):\n def test_x(self): self.assertEqual(f(2),3)\n')
            instruction='Fix the regression in src/core.py. Run python -m unittest discover -s tests. Do not alter tests or src/api.py.'
            test, targets=locate(instruction,root)
            self.assertEqual(targets,[root/'src/core.py'])
            self.assertFalse(run_suite(root,test)[0])
            task=Task('coding_a','coding',instruction,1,'unittest',root)
            llm=type('Fake',(),{})()
            llm.chat=AsyncMock(return_value={'content':'```python\ndef f(x): return x+1\n```','cost':1})
            result=await llm_solvers.solve_coding(llm,task)
            self.assertEqual(result[0],'fixed')
            self.assertEqual(llm.chat.await_count,1)
            self.assertEqual((root/'src/core.py').read_text(),'def f(x): return x-1\n')
            h=Harness(root,None)
            self.assertTrue(h.accept_code(task,result[1],'test'))
