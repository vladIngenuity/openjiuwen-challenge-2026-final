#!/usr/bin/env python3
"""Entry point:  python /app/run_agent.py --tasks-dir /data/tasks [--out FILE]

Env: TASKS, OUT, LLM_BASE_URL, LLM_API_KEY, BUDGET (default 100000).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import tempfile
from pathlib import Path

if os.name == "nt" and not sys.flags.utf8_mode:
    # Windows dev machines: force UTF-8 file I/O for us and every child process
    import subprocess as _sp
    os.environ["PYTHONUTF8"] = "1"
    sys.exit(_sp.call([sys.executable, "-X", "utf8", *sys.argv]))
sys.dont_write_bytecode = True
APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))


def _prepare_runtime():
    # Container runs with --read-only and HOME=/tmp.  openJiuwen writes logs to
    # ./logs relative to CWD, so work from a writable scratch dir.
    tmp = os.environ.get("TMPDIR") or ("/tmp" if os.name != "nt" else tempfile.gettempdir())
    if not os.path.isdir(tmp) or not os.access(tmp, os.W_OK):
        tmp = tempfile.gettempdir()
    run_dir = Path(tmp) / "harness_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = tmp
    os.environ.setdefault("HOME", tmp)
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    os.environ.setdefault("SSRF_PROTECT_ENABLED", "false")
    os.environ.setdefault("MPLCONFIGDIR", str(run_dir / "mpl"))
    os.environ.setdefault("HF_HOME", str(run_dir / "hf"))
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.chdir(run_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-dir", default=os.environ.get("TASKS", "/data/tasks"))
    ap.add_argument("--out", default=os.environ.get("OUT"))
    ap.add_argument("--strategy", default=os.environ.get("HARNESS_STRATEGY", "baseline"),
                    help="baseline (default) | legacy | any name in harness/strategies")
    args = ap.parse_args()
    tasks_dir = Path(args.tasks_dir).resolve()
    out = args.out
    if out and not os.path.isabs(out):
        out = str(Path.cwd() / out)
    for variable in ("HARNESS_TRACE", "HARNESS_REQUEST_JOURNAL"):
        if os.environ.get(variable):
            os.environ[variable] = str(Path(os.environ[variable]).resolve())
    _prepare_runtime()

    from harness.log import log
    from harness.pipeline import Harness

    if not tasks_dir.is_dir():
        log(f"tasks dir {tasks_dir} not found")
        return 2
    h = Harness(tasks_dir, out, strategy=args.strategy)
    def terminate(signum, frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        asyncio.run(h.run())
    except KeyboardInterrupt:
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    sys.exit(main())
