"""Grade completed public runs locally, without model clients or answer export.

Only aggregate results are printable. Per-task grading bits remain in a local
sidecar outside Git; private reference values and hidden source are never saved.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile

from harness import sandbox


from .common import guard, in_checkout


def grade_run(tasks, trace, private, out):
    tasks,trace,private,out=map(guard,(tasks,trace,private,out))
    if sandbox.ISOLATION!='strict': raise ValueError('Private grading requires strict isolation')
    data=json.loads(trace.read_text())
    if data.get('calls') or data.get('spent')!=0: raise ValueError('Expected completed zero-model run')
    if in_checkout(out):
        raise ValueError('Store private grading sidecars outside Git')
    specs={}
    for p in sorted(tasks.glob('*/task.json')):
        if p.is_symlink() or p.parent.is_symlink(): raise ValueError('Symlinked input')
        spec=json.loads(p.read_text());tid=spec['task_id']
        if tid!=p.parent.name or re.search(r'batch[-_]0*23',tid,re.I): raise ValueError('Invalid/protected task identity')
        specs[tid]=spec
    private_digest=sha256(private.read_bytes()).hexdigest()
    # This archive is opened only by the grading process, after all solver runs.
    with ZipFile(private) as archive:
        truth=json.loads(archive.read('truth.json'))
    if set(truth)!=set(specs): raise ValueError('Public/private identity mismatch')
    per=defaultdict(Counter); sidecar=[]
    for tid,spec in sorted(specs.items()):
        gold=truth[tid];kind=spec['task_type'];record=data.get('results',{}).get(tid,{})
        if gold['type']!=kind or float(gold['reward'])!=float(spec['reward']):
            raise ValueError('Public/private metadata mismatch')
        m=per[kind];m['tasks']+=1
        claimed=record.get('status')=='verified';m['internally_verified']+=claimed
        m['feasible']+=bool(gold['feasible']);m['infeasible']+=not gold['feasible']
        answer=tasks/tid/'answer.txt'
        submitted=answer.read_text().strip() if answer.is_file() and not answer.is_symlink() else None
        m['infeasible_claims']+=submitted=='INFEASIBLE'
        m['false_infeasible']+=bool(gold['feasible'] and submitted=='INFEASIBLE')
        public=hidden=None;correct=False
        if not gold['feasible']:
            # Contest reward for detecting infeasibility is zero.
            m['correct_infeasible']+=submitted=='INFEASIBLE'
            m['skipped_infeasible']+=submitted is None
        elif kind=='coding':
            workspace=tasks/tid/'workspace'
            with tempfile.TemporaryDirectory(prefix='private-grade-') as temp:
                stage=Path(temp);sandbox.copy_inputs(workspace,stage)
                suite=stage/'test_mylib.py'
                public,_=sandbox.run_suite(stage,suite,timeout=15)
            if public:
                with tempfile.TemporaryDirectory(prefix='private-grade-') as temp:
                    stage=Path(temp);sandbox.copy_inputs(workspace,stage)
                    hidden,_=sandbox.run_suite(stage,None,timeout=15,hidden_source=gold['_hidden'])
            else: hidden=False
            correct=bool(public and hidden)
            m['public_pass']+=bool(public);m['hidden_pass']+=bool(hidden)
        else:
            correct=submitted is not None and submitted==gold['expected'].strip()
        if gold['feasible']:
            m['max_reward']+=float(spec['reward'])
            m['true_correct']+=correct
            m['true_reward']+=float(spec['reward']) if correct else 0
            m['unresolved_feasible']+=not correct
        m['false_internal_verified']+=bool(claimed and not correct)
        m['skipped_or_unreported']+=record.get('status','pending') in ('pending','skipped')
        sidecar.append(dict(task_id=tid,type=kind,public_pass=public,hidden_pass=hidden,
                            true_correct=bool(correct),internal_verified=claimed))
    totals=Counter()
    for metrics in per.values(): totals.update(metrics)
    result=dict(schema_version=1,private_archive_sha256=private_digest,model_calls=0,
        verification='separate grading process; hidden assertions never model input',
        totals=dict(totals),per_type={k:dict(v) for k,v in sorted(per.items())},
        limitations=['Passing tests is evidence for this finite suite, not proof for every input.',
            'The completion protocol rejects stdout/early-exit spoofing and basic framework tampering; arbitrary in-process Python remains outside a complete hostile-code trust boundary.'])
    out.mkdir(parents=True,exist_ok=True)
    public_result=out/'aggregate.json';public_result.write_text(json.dumps(result,indent=2)+'\n')
    bits=out/'grading-bits.local.json';bits.write_text(json.dumps(sidecar,indent=2)+'\n');bits.chmod(0o600)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tasks',type=Path,required=True);p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--private',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try: print(json.dumps(grade_run(a.tasks,a.trace,a.private,a.out),indent=2))
    except Exception:
        # No traceback or exception values: private test data must not escape.
        p.exit(2,'Private grading failed; no reference values exported.\n')


if __name__=='__main__':main()
