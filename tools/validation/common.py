"""Filesystem guards shared without importing the private grader."""
from pathlib import Path
import re


def guard(path):
    path=Path(path).resolve()
    if re.search(r'batch[-_]0*23(?:\D|$)',str(path),re.I):
        raise ValueError('Protected final holdout path')
    return path


def in_checkout(path):
    return any((p/'.git').is_file() or (p/'.git'/'HEAD').is_file() for p in (path,*path.parents))
