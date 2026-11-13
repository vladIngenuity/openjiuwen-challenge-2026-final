"""Private grader positive/negative controls; exports aggregate counts only."""
import argparse
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile

from harness import sandbox
from .common import guard, in_checkout


def controls(public,private):
    public,private=map(guard,(public,private))
    if sandbox.ISOLATION!='strict': raise ValueError('Strict isolation required')
    counts={'coding_tasks':0,'reference_public_pass':0,'reference_hidden_pass':0,'original_hidden_pass':0}
    with ZipFile(public) as pub,ZipFile(private) as secret:
        truth=json.loads(secret.read('truth.json'))
        for tid,gold in sorted(truth.items()):
            if gold['type']!='coding':continue
            if Path(tid).name!=tid:raise ValueError('Invalid task ID')
            counts['coding_tasks']+=1
            prefix=f'tasks/{tid}/workspace/'
            files={name[len(prefix):]:pub.read(name) for name in pub.namelist()
                   if name.startswith(prefix) and not name.endswith('/')}
            def check(reference,hidden):
                with tempfile.TemporaryDirectory(prefix='private-control-') as temp:
                    root=Path(temp)
                    for name,content in files.items():
                        target=root/name
                        if not target.resolve().is_relative_to(root):raise ValueError('Unsafe input path')
                        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
                    if reference:(root/'mylib.py').write_bytes(secret.read(f'reference/{tid}/mylib.py'))
                    return sandbox.run_suite(root,None if hidden else root/'test_mylib.py',
                        timeout=15,hidden_source=gold['_hidden'] if hidden else None)[0]
            counts['reference_public_pass']+=check(True,False)
            counts['reference_hidden_pass']+=check(True,True)
            counts['original_hidden_pass']+=check(False,True)
    counts['positive_controls_valid']=(counts['reference_public_pass']==counts['reference_hidden_pass']==counts['coding_tasks'])
    return counts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--public',type=Path,required=True);p.add_argument('--private',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:
        out=guard(a.out)
        if in_checkout(out):raise ValueError('Output must be outside Git')
        result=controls(a.public,a.private);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
        if not result['positive_controls_valid']:raise SystemExit(1)
    except Exception:p.exit(2,'Private controls failed; no reference values exported.\n')


if __name__=='__main__':main()
