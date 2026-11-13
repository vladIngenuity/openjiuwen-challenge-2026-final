"""Synthetic grading fixtures only; no actual holdout/reference archives."""
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from unittest.mock import patch

from tools.validation.grade_archive import grade_run
from tools.validation.common import guard, in_checkout
from tools.validation.run_public import run_public


class GraderSeparation(unittest.TestCase):
    def test_public_pass_is_not_private_correctness_and_no_reference_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);tasks=root/'tasks';task=tasks/'fixture';work=task/'workspace';work.mkdir(parents=True)
            spec=dict(task_id='fixture',task_type='coding',reward=7,check='unittest',instruction='public')
            (task/'task.json').write_text(json.dumps(spec))
            (work/'mylib.py').write_text('def f():return 4\n')
            (work/'test_mylib.py').write_text('import unittest\nfrom mylib import f\nclass T(unittest.TestCase):\n    def test_public(self):self.assertGreater(f(),0)\n')
            hidden='# fixture-private-source-marker\nimport unittest\nfrom mylib import f\nclass T(unittest.TestCase):\n    def test_hidden(self):self.assertEqual(f(),5)\n'
            private=root/'private.zip'
            with ZipFile(private,'w') as z:
                z.writestr('truth.json',json.dumps({'fixture':dict(type='coding',reward=7,feasible=True,
                    expected='fixture-private-answer-marker',_hidden=hidden)}))
            trace=root/'trace.json';trace.write_text(json.dumps(dict(calls=[],spent=0,
                results={'fixture':dict(status='verified')})))
            result=grade_run(tasks,trace,private,root/'first')
            self.assertEqual(result['totals']['public_pass'],1)
            self.assertEqual(result['totals']['true_correct'],0)
            self.assertEqual(result['totals']['false_internal_verified'],1)
            exported=(root/'first'/'aggregate.json').read_text()+(root/'first'/'grading-bits.local.json').read_text()
            self.assertNotIn('fixture-private-source-marker',exported)
            self.assertNotIn('fixture-private-answer-marker',exported)
            self.assertEqual((root/'first'/'grading-bits.local.json').stat().st_mode&0o777,0o600)
            (work/'mylib.py').write_text('def f():return 5\n')
            result=grade_run(tasks,trace,private,root/'second')
            self.assertEqual(result['totals']['true_correct'],1)
            self.assertEqual(result['totals']['true_reward'],7)

    def test_protected_path_fails_before_archive_access(self):
        with patch('tools.validation.grade_archive.ZipFile',side_effect=AssertionError('Forbidden archive access')):
            with self.assertRaises(ValueError):
                grade_run('/tmp/tasks','/tmp/trace.json','/tmp/batch-023.private.zip','/tmp/out')

    def test_public_runner_rejects_private_fields_before_starting_process(self):
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();(source/'run_agent.py').write_text('raise AssertionError("must not run")')
            data=json.dumps({'task_id':'t','expected':'fixture-secret'}).encode()
            public=root/'public.zip'
            with ZipFile(public,'w') as z:z.writestr('tasks/t/task.json',data)
            inventory=root/'inventory.json';inventory.write_text(json.dumps(dict(batch='batch-022',tasks=[{}],
                files=[dict(path='tasks/t/task.json',sha256=sha256(data).hexdigest())])))
            with patch('tools.validation.run_public.subprocess.Popen',side_effect=AssertionError('No process allowed')):
                with self.assertRaises(ValueError):run_public(source,public,inventory,root/'out')

    def test_actual_checkout_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'.git').mkdir()
            self.assertFalse(in_checkout(root/'out'))
            (root/'.git'/'HEAD').write_text('ref: refs/heads/main')
            self.assertTrue(in_checkout(root/'out'))
