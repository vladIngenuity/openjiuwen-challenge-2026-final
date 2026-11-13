"""Run a frozen public corpus with model access disabled. No private input option."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import time
from zipfile import ZipFile

from .common import guard, in_checkout


def run_public(source,public,inventory,out,task_seconds=30.,phase_seconds=90.):
    source,public,inventory,out=map(guard,(source,public,inventory,out))
    if (out/'trace.json').exists() or (out/'tasks').exists(): raise ValueError('Fresh output directory required')
    if in_checkout(out): raise ValueError('Output must be outside Git')
    if not (source/'run_agent.py').is_file(): raise ValueError('Missing harness source')
    inv=json.loads(inventory.read_text());expected={f['path']:f for f in inv['files']}
    if inv['batch']!='batch-022': raise ValueError('This validation authorizes batch-022 only')
    out.mkdir(parents=True,exist_ok=True)
    with ZipFile(public) as z:
        files=[f for f in z.infolist() if not f.is_dir()]
        if len(files)!=len(expected) or {f.filename for f in files}!=set(expected):
            raise ValueError('Inventory mismatch or duplicate paths')
        if sum(f.file_size for f in files)>64*1024**2: raise ValueError('Oversized corpus')
        for f in files:
            p=PurePosixPath(f.filename)
            if p.is_absolute() or '..' in p.parts or p.parts[0]!='tasks' or '\\' in f.filename:
                raise ValueError('Unsafe public archive path')
            if (f.external_attr>>16)&0o170000==0o120000: raise ValueError('Symlink in public corpus')
            content=z.read(f)
            if sha256(content).hexdigest()!=expected[f.filename]['sha256']: raise ValueError('Public fingerprint mismatch')
            if p.name=='task.json':
                spec=json.loads(content)
                if set(spec)&{'expected','_hidden','reference','answer','hidden_tests'}:
                    raise ValueError('Private fields in public task')
            target=out/f.filename;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    home=out/'home';home.mkdir()
    env={'PATH':str(Path(sys.executable).parent)+':/usr/local/bin:/usr/bin:/bin','HOME':str(home),
        'PYTHONPATH':str(source),'HARNESS_ISOLATION':'strict','BUDGET':'100000',
        'HARNESS_TRACE':str(out/'trace.json'),'PYTHONDONTWRITEBYTECODE':'1',
        'HARNESS_DET_TASK_SECONDS':str(task_seconds),'HARNESS_DET_PHASE_SECONDS':str(phase_seconds)}
    inputs=sorted((source/'harness').rglob('*.py'))+[source/'run_agent.py']
    code_sha=sha256(json.dumps({str(p.relative_to(source)):sha256(p.read_bytes()).hexdigest()
                               for p in inputs},sort_keys=True).encode()).hexdigest()
    start=time.perf_counter()
    with (out/'solver.log').open('w') as log:
        child=subprocess.Popen([sys.executable,str(source/'run_agent.py'),'--tasks-dir',str(out/'tasks'),
            '--strategy','baseline','--out',str(out/'results.json')],cwd=source,env=env,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try: status=child.wait(timeout=300)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);status=child.wait()
    duration=time.perf_counter()-start
    trace=json.loads((out/'trace.json').read_text())
    if trace.get('calls') or trace.get('spent')!=0: raise ValueError('Unexpected model activity')
    statuses=Counter(r['status'] for r in trace['results'].values())
    statuses['unreported_pending']+=len(inv['tasks'])-len(trace['results'])
    report=dict(source_code_sha256=code_sha,public_sha256=sha256(public.read_bytes()).hexdigest(),
        batch='batch-022',tasks=len(inv['tasks']),wall_seconds=duration,returncode=status,
        statuses=dict(statuses),model_calls=0,spent=0,det_task_seconds=task_seconds,det_phase_seconds=phase_seconds,
        private_access=False,isolation='strict')
    (out/'public-run.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','public','inventory','out'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--task-seconds',type=float,default=30);p.add_argument('--phase-seconds',type=float,default=90)
    a=p.parse_args()
    print(json.dumps(run_public(a.source,a.public,a.inventory,a.out,a.task_seconds,a.phase_seconds),indent=2))


if __name__=='__main__':main()
