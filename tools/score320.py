#!/usr/bin/env python3
"""Private offline grader. Never import candidate code into the evaluator process.
Public Coding suites are restored from pristine inputs. Differential checks compare
JSON observations from separate isolated reference and candidate subprocesses.
These local tests do not establish official hidden-test correctness.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter, defaultdict
import json
from pathlib import Path
import shutil
import sys
import tempfile
if __package__ in (None, ''): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import sandbox
from harness.solvers.coding_solver import locate
from harness.tasks import _atomic_write


def probes_from_tests(source, function):
    probes = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != function:
            continue
        try:
            args = [ast.literal_eval(a) for a in node.args]
            kwargs = {k.arg: ast.literal_eval(k.value) for k in node.keywords if k.arg}
            if len(kwargs) != len(node.keywords): continue
            json.dumps([args, kwargs], allow_nan=False)
        except (ValueError, TypeError, SyntaxError): continue
        probes.append([args, kwargs])
        for index, arg in enumerate(args):
            variants = []
            if isinstance(arg, str): variants = ['', ' ', arg+arg, arg.upper(), arg.lower(), ' '+arg+' ', arg[::-1], '\t'+arg+'\n']
            elif type(arg) is int: variants = [0, 1, -1, arg-1, arg+1, arg*2]
            elif isinstance(arg, list): variants = [[], arg[:1], arg[::-1], arg+arg]
            elif isinstance(arg, dict): variants = [{}, dict(reversed(list(arg.items())))]
            for value in variants:
                changed=list(args); changed[index]=value; probes.append([changed, kwargs])
    unique={json.dumps(p, sort_keys=True, ensure_ascii=False):p for p in probes}
    return list(unique.values())[:128]


def observe(workspace, module, function, probes, timeout):
    # The child sees inputs, never the expected outputs or reference source.
    program = f'''import importlib, json
module=importlib.import_module({module!r})
fn=getattr(module,{function!r})
observations=[]
for args, kwargs in {probes!r}:
 try:
  value=fn(*args, **kwargs)
  json.dumps(value, allow_nan=False)
  observations.append(["value",value])
 except Exception as error:
  observations.append(["exception",type(error).__name__])
print("__OBSERVATIONS__"+json.dumps(observations,ensure_ascii=False,allow_nan=False))
'''
    rc, output=sandbox.run_python(program,workspace,timeout=timeout)
    lines=[line[len('__OBSERVATIONS__'):] for line in output.splitlines() if line.startswith('__OBSERVATIONS__')]
    if rc or len(lines)!=1: return None
    try: value=json.loads(lines[0])
    except ValueError: return None
    return value if isinstance(value,list) and len(value)==len(probes) else None


def grade_code(candidate, pristine, private, tid, timeout=10):
    spec=json.loads((pristine/'task.json').read_text())
    original=pristine/'workspace' if (pristine/'workspace').is_dir() else pristine
    submitted=candidate/'workspace' if (candidate/'workspace').is_dir() else candidate
    test, targets=locate(spec['instruction'],original)
    if not test or not targets: return {'verdict':'coding_unsupported'}
    with tempfile.TemporaryDirectory(prefix='grade320-') as tmp:
        stage=Path(tmp)/'candidate'; sandbox.copy_inputs(original,stage)
        # Only permitted source targets cross the boundary; no model-written tests.
        for target in targets:
            relative=target.relative_to(original); incoming=submitted/relative
            if (not incoming.is_file() or incoming.is_symlink()
                    or not incoming.resolve().is_relative_to(submitted.resolve())):
                return {'verdict':'coding_missing_source'}
            shutil.copyfile(incoming,stage/relative)
        public_ok,_=sandbox.run_suite(stage,stage/test.relative_to(original),timeout)
        reference=Path(tmp)/'reference'; sandbox.copy_inputs(original,reference)
        number=int(tid.rsplit('_',1)[1])
        if number < 40:
            ref=private/'original_coding_reference'/f'{number:04d}.py'
            if not ref.is_file(): return {'verdict':'coding_reference_missing','public_pass':public_ok}
            shutil.copyfile(ref,reference/targets[0].relative_to(original))
            functions=[n.name for n in ast.parse(ref.read_text()).body if isinstance(n,ast.FunctionDef)]
            if len(functions)!=1: return {'verdict':'coding_reference_unsupported','public_pass':public_ok}
            function=functions[0]; module=targets[0].relative_to(original).with_suffix('').as_posix().replace('/','.')
        else:
            ref=private/'coding_reference'/tid/'src/core.py'
            if not ref.is_file(): return {'verdict':'coding_reference_missing','public_pass':public_ok}
            shutil.copyfile(ref,reference/'src/core.py'); module,function='src.api','execute'
        test_files=sorted(test.rglob('test*.py')) if test.is_dir() else [test]
        source='\n'.join(p.read_text() for p in test_files)
        probes=probes_from_tests(source,function)
        if not probes: return {'verdict':'coding_no_probes','public_pass':public_ok}
        expected=observe(reference,module,function,probes,timeout)
        if expected is None: return {'verdict':'coding_oracle_error','public_pass':public_ok}
        # Do not award success based only on matching exceptions for invalid inputs.
        valid=[i for i,x in enumerate(expected) if x[0]=='value']
        if not valid: return {'verdict':'coding_no_valid_probes','public_pass':public_ok}
        actual=observe(stage,module,function,probes,timeout)
        matches=sum(actual[i]==expected[i] for i in range(len(probes))) if actual else 0
        ok=public_ok and actual==expected
        return {'verdict':'coding_local_pass' if ok else 'coding_wrong', 'public_pass':public_ok,
                'probes':len(probes),'valid_probes':len(valid),'matching_probes':matches}


def evaluate(tasks, source, private, trace=None, timeout=10, task_ids=None):
    truth=json.loads((private/'truth.json').read_text()); manifest=json.loads((private/'manifest.json').read_text())
    rewards={r['task_id']:r['reward'] for r in manifest}
    if set(truth)!=set(rewards): raise ValueError('truth/manifest task IDs differ')
    ids=sorted(task_ids if task_ids is not None else truth)
    if not set(ids)<=set(truth): raise ValueError('unknown selected tasks')
    records=(trace or {}).get('results',{}); rows=[]
    for tid in ids:
        if Path(tid).name!=tid or tid in {'.','..'}: raise ValueError('unsafe task id')
        entry=truth[tid]; directory=tasks/tid
        if directory.is_symlink(): raise ValueError('symlinked submission')
        answer_file=directory/'answer.txt'
        answer=answer_file.read_text(errors='replace').strip() if answer_file.is_file() and not answer_file.is_symlink() else None
        status=records.get(tid,{}).get('status','unknown')
        refusal=answer in {'IMPOSSIBLE','INFEASIBLE'} or status=='infeasible_claimed'
        row={'task_id':tid,'category':entry['category'],'solvable':entry['solvable'],
             'reward':rewards[tid],'answer_present':answer is not None,'refusal':refusal,'status':status}
        if not entry['solvable']: row['verdict']='true_refusal' if refusal else 'impossible_not_recognized'
        elif refusal: row['verdict']='false_refusal'
        elif entry['check']=='unittest': row.update(grade_code(directory,source/tid,private,tid,timeout))
        else: row['verdict']='missing' if answer is None else ('correct_text' if answer==str(entry['expected']).strip() else 'wrong_text')
        rows.append(row)
    calls=(trace or {}).get('calls',[]); per={}
    for cat in ('math','search','data_analysis','coding'):
        subset=[r for r in rows if r['category']==cat]; tids={r['task_id'] for r in subset}
        cc=[c for c in calls if c.get('tag','').split(':')[1:2] and c.get('tag','').split(':')[1] in tids]
        per[cat]={'tasks':len(subset),'verdicts':dict(Counter(r['verdict'] for r in subset)),
                  'local_reward':sum(r['reward'] for r in subset if r['verdict'] in {'correct_text','coding_local_pass'}),
                  'physical_sends':len(cc),'confirmed_cost':sum(c['cost'] for c in cc if c.get('accounting')=='usage'),
                  'uncertain_reserved':sum(c['cost'] for c in cc if c.get('accounting')!='usage')}
    return {'grading':'local differential tests + pristine public tests; not official hidden correctness',
            'rows':rows,'per_category':per,'local_reward':sum(p['local_reward'] for p in per.values()),
            'verdicts':dict(Counter(r['verdict'] for r in rows)),
            'false_refusals':sum(r['verdict']=='false_refusal' for r in rows),
            'true_refusals':sum(r['verdict']=='true_refusal' for r in rows),
            'impossible_tasks':sum(not r['solvable'] for r in rows),
            'unprocessed':sum(r['status'] in {'pending','skipped'} for r in rows),
            'status_unavailable':sum(r['status']=='unknown' for r in rows),
            'physical_sends':len(calls),'api_errors':dict(Counter(str(c.get('http_status')) for c in calls if c.get('http_status'))),
            'confirmed_cost':sum(c['cost'] for c in calls if c.get('accounting')=='usage'),
            'uncertain_reserved':sum(c['cost'] for c in calls if c.get('accounting')!='usage'),
            'seconds':(trace or {}).get('seconds')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('tasks','source','private','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--trace',type=Path); p.add_argument('--timeout',type=float,default=10)
    a=p.parse_args(); tr=json.loads(a.trace.read_text()) if a.trace else None
    result=evaluate(a.tasks,a.source,a.private,tr,a.timeout)
    _atomic_write(a.output,json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
if __name__=='__main__': main()
