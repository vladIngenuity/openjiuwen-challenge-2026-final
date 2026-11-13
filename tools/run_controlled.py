#!/usr/bin/env python3
"""Prepare immutable research shards or 100-task contest episodes, then run once.
No secrets, evaluator references or inherited HARNESS overrides enter the plan.
A crashed/uncertain episode is never restarted. Research shards have independent
budgets; competition episodes use exactly one ledger and deadline per strategy.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import time
if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.tasks import _atomic_write
from harness.sandbox import copy_inputs

ROOT=Path(__file__).resolve().parents[1]
MODELS={'always_reason':'qwen3.8-27b','always_fast':'qwen3.8-27b-noreason','baseline':None,
        'always_reason_no_vote':'qwen3.8-27b','reason_first_bounded':'qwen3.8-27b',
        'empirical_hybrid':None}

def digest_tree(root, exclude=()):
    hashes={}
    for path in sorted(root.rglob('*')):
        if any(part in exclude for part in path.relative_to(root).parts): continue
        if path.is_symlink(): raise ValueError('symlinks are not valid experiment inputs')
        if path.is_file(): hashes[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes

def code_digest():
    files={}
    for name in ('harness','tools'):
        for path in sorted((ROOT/name).rglob('*.py')):
            files[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    files['run_agent.py']=hashlib.sha256((ROOT/'run_agent.py').read_bytes()).hexdigest()
    return files

def prepare(args):
    source=args.source.resolve(); output=args.output.resolve()
    if output.exists(): raise ValueError('output exists; prepare a fresh run')
    if source==output or source in output.parents: raise ValueError('output must be outside source')
    grouped={name:[] for name in ('math','search','data_analysis','coding')}
    for task in sorted(source.glob('*/task.json')):
        if task.is_symlink() or task.parent.is_symlink(): raise ValueError('symlinked task')
        spec=json.loads(task.read_text()); category=spec['task_type']
        if category not in grouped: raise ValueError('unexpected task category')
        if spec.get('task_id',task.parent.name)!=task.parent.name: raise ValueError('task id/directory mismatch')
        if any(k in spec for k in ('expected','_hidden','solvable')): raise ValueError('private labels in task spec')
        grouped[category].append(task.parent.name)
    if any(len(ids)!=80 for ids in grouped.values()): raise ValueError('expected 80 tasks per category')
    rng=random.Random(args.seed)
    for ids in grouped.values(): rng.shuffle(ids)
    groups=([list(chunk) for chunk in zip(*grouped.values())] if args.mode=='research'
            else [[tid for ids in grouped.values() for tid in ids[:25]]])
    budget=30000 if args.mode=='research' else 100000
    deadline=1200 if args.mode=='research' else 3300
    output.mkdir(parents=True)
    # Freeze only public input files; no expected/private data in child workspace.
    pristine=output/'inputs'; pristine.mkdir()
    selected=sorted({tid for group in groups for tid in group})
    for tid in selected:
        copy_inputs(source/tid,pristine/tid,skip={'answer.txt','__pycache__','.git'})
    config={'schema':1,'created_utc':datetime.now(timezone.utc).isoformat(),
            'mode':args.mode,'seed':args.seed,'strategies':args.strategies,'groups':groups,
            'budget_per_episode':budget,'deadline_per_episode':deadline,
            'concurrency':args.concurrency,'reasoning_usage':args.reasoning_usage,
            'input_sha256':digest_tree(pristine),'code_sha256':code_digest(),
            'note':'research shards are not a single contest-budget experiment',
            'python':sys.version,'python_executable':sys.executable,
            'models':{s:MODELS[s] for s in args.strategies}}
    _atomic_write(output/'plan.json',json.dumps(config,indent=2))
    print(output/'plan.json')


def journal_summary(path):
    started={};settled={};not_sent=set();malformed=0
    if path.exists():
        for line in path.read_text().splitlines():
            try: r=json.loads(line)
            except ValueError: malformed+=1;continue
            request_id=r.get('request_id')
            if r['event']=='dispatch': started[request_id]=r
            elif r['event']=='settled': settled[request_id]=r
            elif r['event']=='not_sent': not_sent.add(request_id)
    unresolved=set(started)-set(settled)-not_sent
    return {'settled_calls':len(settled),'unresolved_dispatches':len(unresolved),
            'confirmed_cost':sum(r['cost'] for r in settled.values() if r.get('accounting')=='usage'),
            'uncertain_reserved':sum(r['cost'] for r in settled.values() if r.get('accounting')!='usage'),
            'unresolved_reserved':sum(started[r]['reserved'] for r in unresolved),'malformed_lines':malformed}


def execute(plan_path):
    plan_path=plan_path.resolve();root=plan_path.parent;plan=json.loads(plan_path.read_text())
    if not os.getenv('LLM_BASE_URL') or not os.getenv('LLM_API_KEY'):
        raise ValueError('set LLM_BASE_URL and LLM_API_KEY in the launching shell; do not put keys in the plan')
    if not plan.get('reasoning_usage'): raise ValueError('prepare with a verified --reasoning-usage contract')
    if digest_tree(root/'inputs')!=plan['input_sha256']: raise ValueError('public inputs changed')
    if code_digest()!=plan['code_sha256']: raise ValueError('code changed; prepare a fresh plan')
    # Offline constructor preflight: controlled runs require the pinned SDK to initialize.
    # This avoids silently comparing raw and SDK transports across configurations.
    from harness.llm import LLM, MODEL_REASON
    from harness.budget import BudgetLedger
    with __import__('unittest.mock',fromlist=['patch']).patch.dict(os.environ,
            {'LLM_BASE_URL':'https://example.invalid/v1','LLM_API_KEY':'offline-preflight'}):
        try: LLM(BudgetLedger())._oj_model(MODEL_REASON)
        except Exception as error:
            raise ValueError('SDK initialization failed: '+type(error).__name__+'; run tools/diagnose_sdk.py') from None
    # New process ownership marker prevents re-sending after partial/unknown outcomes.
    with (root/'STARTED').open('x') as stream: stream.write(datetime.now(timezone.utc).isoformat())
    versions={}
    for name in ('openjiuwen','openai','httpx','pydantic'):
        try: versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name]=None
    _atomic_write(root/'runtime.json',json.dumps({'python':sys.version,'executable':sys.executable,'packages':versions},indent=2))
    reports=[]
    for strategy in plan['strategies']:
        for index,ids in enumerate(plan['groups']):
            episode=root/strategy/f'{index:03d}';tasks=episode/'tasks';tasks.mkdir(parents=True)
            for tid in ids: copy_inputs(root/'inputs'/tid,tasks/tid,skip={'answer.txt','__pycache__','.git'})
            env={k:v for k,v in os.environ.items() if not k.startswith(('HARNESS_','LLM_')) and k not in {'TASKS','OUT','BUDGET'}}
            env.update(LLM_BASE_URL=os.environ['LLM_BASE_URL'],LLM_API_KEY=os.environ['LLM_API_KEY'],
                       BUDGET=str(plan['budget_per_episode']),HARNESS_TIME_LIMIT=str(plan['deadline_per_episode']),
                       HARNESS_REASONING_USAGE=plan['reasoning_usage'],HARNESS_ISOLATION='strict',
                       LLM_CONCURRENCY=str(plan['concurrency']),HARNESS_WORKERS=str(plan['concurrency']),
                       HARNESS_TRACE=str(episode/'trace.json'),HARNESS_REQUEST_JOURNAL=str(episode/'requests.jsonl'))
            if MODELS[strategy]: env['HARNESS_PIN_MODEL']=MODELS[strategy]
            _atomic_write(episode/'config.json',json.dumps({k:v for k,v in env.items() if k.startswith('HARNESS_') or k in {'BUDGET','LLM_CONCURRENCY'}},indent=2))
            started=time.monotonic();timeout=False
            with (episode/'run.log').open('w') as log:
                process=subprocess.Popen([sys.executable,str(ROOT/'run_agent.py'),'--strategy',strategy,
                                          '--tasks-dir',str(tasks),'--out',str(episode/'results.json')],
                                         cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    code=process.wait(timeout=plan['deadline_per_episode']+30)
                except subprocess.TimeoutExpired:
                    timeout=True;process.terminate()
                    try: code=process.wait(timeout=10)
                    except subprocess.TimeoutExpired: process.kill();code=process.wait()
                finally:
                    # Sandbox children create their own process group and have their own limits.
                    if process.poll() is None: process.terminate();process.wait(timeout=10)
            report={'strategy':strategy,'episode':index,'tasks':ids,'exit_code':code,
                    'timed_out':timeout,'seconds':round(time.monotonic()-started,3),
                    **journal_summary(episode/'requests.jsonl')}
            reports.append(report)
            _atomic_write(root/'summary.json',json.dumps({'plan':str(plan_path),'episodes':reports},indent=2))
            print(json.dumps(report),flush=True)
    _atomic_write(root/'COMPLETED','completed\n')


def score_plan(plan_path, private):
    from tools.score320 import evaluate
    plan_path=plan_path.resolve(); root=plan_path.parent; plan=json.loads(plan_path.read_text())
    if digest_tree(root/'inputs')!=plan['input_sha256']: raise ValueError('public inputs changed')
    summaries=[]
    for strategy in plan['strategies']:
        combined=[]; spent=uncertain=seconds=0.; sends=unprocessed=0
        for index,ids in enumerate(plan['groups']):
            episode=root/strategy/f'{index:03d}'
            if not (episode/'tasks').is_dir():
                unprocessed+=len(ids); continue
            path=episode/'trace.json'
            if path.is_file(): trace=json.loads(path.read_text())
            else:
                # Recover settled sends after a hard kill. Unresolved dispatches stay separate.
                results=episode/'results.json'
                records=json.loads(results.read_text()).get('results',[]) if results.is_file() else []
                trace={'calls':[],'results':{r['task_id']:r for r in records}}
                journal=episode/'requests.jsonl'
                if journal.is_file():
                    for line in journal.read_text().splitlines():
                        try: event=json.loads(line)
                        except ValueError: continue
                        if event.get('event')=='settled': trace['calls'].append(event)
            result=evaluate(episode/'tasks',root/'inputs',private,trace,task_ids=ids)
            result['journal']=journal_summary(episode/'requests.jsonl')
            _atomic_write(episode/'evaluation.json',json.dumps(result,indent=2))
            combined+=result['rows'];spent+=result['confirmed_cost']
            uncertain+=result['uncertain_reserved']+result['journal']['unresolved_reserved']
            sends+=result['physical_sends'];seconds+=result['seconds'] or 0
        summaries.append({'strategy':strategy,'mode':plan['mode'],
                          'local_reward':sum(r['reward'] for r in combined if r['verdict'] in {'correct_text','coding_local_pass'}),
                          'graded_tasks':len(combined),'episodes_not_run_tasks':unprocessed,
                          'confirmed_cost':spent,'uncertain_or_unresolved_reserved':uncertain,
                          'settled_physical_sends':sends,'observed_seconds':seconds,
                          'warning':'local tests, not official hidden correctness; research budgets reset per shard'})
    _atomic_write(root/'comparison.json',json.dumps(summaries,indent=2))
    print(json.dumps(summaries,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);commands=p.add_subparsers(dest='command',required=True)
    prep=commands.add_parser('prepare');prep.add_argument('--source',type=Path,required=True);prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--mode',choices=('research','competition'),default='research');prep.add_argument('--seed',type=int,default=20261113)
    prep.add_argument('--strategies',nargs='+',choices=MODELS,default=['always_reason','always_fast','baseline']);prep.add_argument('--concurrency',type=int,choices=range(1,6),default=1)
    prep.add_argument('--reasoning-usage',choices=('included','separate'),help='set only after provider contract verification')
    run=commands.add_parser('run');run.add_argument('plan',type=Path)
    score=commands.add_parser('score');score.add_argument('plan',type=Path);score.add_argument('--private',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=='prepare': prepare(args)
        elif args.command=='run': execute(args.plan)
        else: score_plan(args.plan,args.private)
    except (ValueError,FileExistsError) as error: p.error(str(error))
if __name__=='__main__': main()
