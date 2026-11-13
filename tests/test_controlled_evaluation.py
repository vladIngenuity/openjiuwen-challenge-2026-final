import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from tools.score320 import grade_code, evaluate
from tools.run_controlled import prepare, journal_summary

class Grading(unittest.TestCase):
    def test_done_and_tampered_tests_cannot_make_wrong_code_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=root/'source/coding_0000'; candidate=root/'submitted/coding_0000'; private=root/'private'
            for p in (original/'workspace',candidate/'workspace',private/'original_coding_reference'): p.mkdir(parents=True)
            spec={'instruction':'Fix mylib.py. Run python test_mylib.py.'}
            (original/'task.json').write_text(json.dumps(spec))
            test='import unittest\nfrom mylib import f\nclass Test(unittest.TestCase):\n def test_x(self): self.assertEqual(f(2),3)\n'
            (original/'workspace/test_mylib.py').write_text(test)
            (original/'workspace/mylib.py').write_text('def f(x): return x-1\n')
            (private/'original_coding_reference/0000.py').write_text('def f(x): return x+1\n')
            (candidate/'answer.txt').write_text('DONE')
            (candidate/'workspace/test_mylib.py').write_text('raise SystemExit(0)')
            # This overfit patch passes the single public example, fails differential probes.
            (candidate/'workspace/mylib.py').write_text('def f(x): return 3\n')
            result=grade_code(candidate,original,private,'coding_0000')
            self.assertTrue(result['public_pass'])
            self.assertEqual(result['verdict'],'coding_wrong')
            (candidate/'workspace/mylib.py').write_text('def f(x): return x+1\n')
            (candidate/'answer.txt').unlink()
            self.assertEqual(grade_code(candidate,original,private,'coding_0000')['verdict'],'coding_local_pass')
            self.assertEqual((original/'workspace/test_mylib.py').read_text(),test)

    def test_refusal_status_counts_without_awarding_impossible_reward(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); private=root/'private';private.mkdir()
            truth={'math_a':{'category':'math','solvable':False,'expected':'IMPOSSIBLE','check':'exact_str'},
                   'math_b':{'category':'math','solvable':True,'expected':'3','check':'exact_str'}}
            (private/'truth.json').write_text(json.dumps(truth))
            (private/'manifest.json').write_text(json.dumps([{'task_id':tid,'reward':10} for tid in truth]))
            tr={'results':{tid:{'status':'infeasible_claimed'} for tid in truth}}
            result=evaluate(root/'tasks',root/'source',private,tr)
            self.assertEqual(result['local_reward'],0)
            self.assertEqual(result['true_refusals'],1)
            self.assertEqual(result['false_refusals'],1)

class Runner(unittest.TestCase):
    def test_plan_has_balanced_shards_and_single_budget_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'source'
            for category in ('math','search','data_analysis','coding'):
                for n in range(80):
                    tid=f'{category}_{n:04d}'; p=source/tid;p.mkdir(parents=True)
                    (p/'task.json').write_text(json.dumps({'task_id':tid,'task_type':category,'instruction':'fixture','reward':1}))
                    (p/'answer.txt').write_text('stale')
            for mode in ('research','competition'):
                dest=root/mode
                prepare(Namespace(source=source,output=dest,mode=mode,seed=123,strategies=['always_reason','always_fast','baseline'],concurrency=1,reasoning_usage=None))
                plan=json.loads((dest/'plan.json').read_text())
                self.assertEqual(len(plan['groups']),80 if mode=='research' else 1)
                self.assertEqual(len(plan['groups'][0]),4 if mode=='research' else 100)
                self.assertFalse(list((dest/'inputs').glob('*/answer.txt')))
                self.assertEqual(plan['budget_per_episode'],30000 if mode=='research' else 100000)
                self.assertNotIn('LLM_API_KEY',json.dumps(plan))

    def test_journal_accounts_for_hard_kill_and_setup_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'events'
            entries=[{'event':'dispatch','request_id':'a','reserved':100},
                     {'event':'dispatch','request_id':'b','reserved':200},
                     {'event':'not_sent','request_id':'b'},
                     {'event':'dispatch','request_id':'c','reserved':300},
                     {'event':'settled','request_id':'c','cost':30,'accounting':'usage'}]
            p.write_text('\n'.join(json.dumps(e) for e in entries)+'\n{')
            result=journal_summary(p)
            self.assertEqual(result['unresolved_dispatches'],1)
            self.assertEqual(result['unresolved_reserved'],100)
            self.assertEqual(result['confirmed_cost'],30)
            self.assertEqual(result['malformed_lines'],1)
