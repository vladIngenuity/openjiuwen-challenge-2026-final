"""Trusted -S bootstrap: add explicit installed library roots, never run site/.pth."""
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    script, *args = sys.argv[1:]
    roots = json.loads(os.environ.get('HARNESS_LIBRARY_ROOTS', '[]'))
    for root in roots:
        if not isinstance(root, str) or not Path(root).is_absolute():
            raise ValueError('Invalid trusted Python library root')
        if root not in sys.path: sys.path.append(root)
    sys.argv = [script, *args]
    # This is the public workspace. Files outside it remain denied by Landlock.
    sys.path.insert(0, str(Path(script).resolve().parent))
    runpy.run_path(script, run_name='__main__')


if __name__ == '__main__': main()
