"""Loopback-only process tests: deadline cancellation and controlled-run artifacts."""
import json
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from tools.run_controlled import execute, code_digest, digest_tree, journal_summary

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(importlib.util.find_spec('openjiuwen'),
                     'openJiuwen SDK is required for lifecycle integration tests')
class Lifecycle(unittest.TestCase):
    def server(self, delay=0):
        state={'calls':0,'received':threading.Event(),'release':threading.Event()}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                state['calls']+=1;state['received'].set()
                if delay: state['release'].wait(delay)
                data={'id':'local','object':'chat.completion','created':0,'model':payload['model'],
                      'choices':[{'index':0,'message':{'role':'assistant','content':'42'},'finish_reason':'stop'}],
                      'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}
                body=json.dumps(data).encode()
                try:
                    self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown);self.addCleanup(state['release'].set)
        return f'http://127.0.0.1:{server.server_port}/v1',state

    def test_sigterm_keeps_answer_and_charges_inflight_once(self):
        base,state=self.server(delay=20)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tasks=root/'tasks';tasks.mkdir()
            for tid,category,instruction in [
                ('math_a','math','A warehouse starts with 22 boxes. It ships 4 boxes. How many boxes does it have at the end?'),
                ('search_a','search','What is the code for station Alpha?')]:
                d=tasks/tid;d.mkdir();(d/'task.json').write_text(json.dumps({'task_id':tid,'task_type':category,'instruction':instruction,'check':'exact_str','reward':1}))
                if category=='search':(d/'kb.txt').write_text('Station Alpha code is 42.')
            env={**os.environ,'LLM_BASE_URL':base,'LLM_API_KEY':'local-fixture','HARNESS_WORKERS':'1',
                 'HARNESS_TRACE':str(root/'trace.json'),'HARNESS_REQUEST_JOURNAL':str(root/'events.jsonl'),
                 'HARNESS_DISABLE_DET':'search','HARNESS_TIME_LIMIT':'600','BUDGET':'100000'}
            with (root/'run.log').open('w') as log:
                process=subprocess.Popen([sys.executable,str(ROOT/'run_agent.py'),'--tasks-dir',str(tasks),'--out',str(root/'results.json')],env=env,stdout=log,stderr=log)
                try:
                    self.assertTrue(state['received'].wait(15),'no loopback dispatch')
                    process.send_signal(signal.SIGTERM)
                    self.assertEqual(process.wait(timeout=15),130)
                finally:
                    if process.poll() is None:process.kill();process.wait()
            self.assertEqual((tasks/'math_a/answer.txt').read_text().strip(),'18')
            result=json.loads((root/'trace.json').read_text())
            self.assertEqual(result['halt_reason'],'uncertain_usage')
            self.assertEqual(len(result['calls']),1)
            self.assertEqual(result['calls'][0]['error'],'cancelled')
            self.assertEqual(result['pending_reservations'],0)
            self.assertEqual(len(json.loads((root/'results.json').read_text())['results']),2)
            self.assertEqual(state['calls'],1)
            self.assertEqual(journal_summary(root/'events.jsonl')['unresolved_dispatches'],0)

    def test_controlled_runner_saves_config_trace_answers_and_rejects_restart(self):
        base,state=self.server()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'inputs/search_a';d.mkdir(parents=True)
            (d/'task.json').write_text(json.dumps({'task_id':'search_a','task_type':'search','instruction':'What is the code for station Alpha?','check':'exact_str','reward':1}))
            (d/'kb.txt').write_text('Station Alpha code is 42.')
            plan={'schema':1,'mode':'competition','groups':[['search_a']],'strategies':['reason_first_bounded'],
                  'budget_per_episode':100000,'deadline_per_episode':3300,'concurrency':1,'reasoning_usage':'included',
                  'input_sha256':digest_tree(root/'inputs'),'code_sha256':code_digest()}
            path=root/'plan.json';path.write_text(json.dumps(plan))
            with patch.dict(os.environ,{'LLM_BASE_URL':base,'LLM_API_KEY':'local-fixture'}):
                execute(path)
                with self.assertRaises(FileExistsError):execute(path)
            episode=root/'reason_first_bounded/000'
            for name in ('config.json','trace.json','results.json','requests.jsonl'):self.assertTrue((episode/name).is_file(),name)
            self.assertEqual((episode/'tasks/search_a/answer.txt').read_text().strip(),'42')
            self.assertNotIn('local-fixture',(episode/'config.json').read_text())
            self.assertEqual(state['calls'],1)
