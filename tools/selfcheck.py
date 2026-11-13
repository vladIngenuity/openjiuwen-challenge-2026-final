#!/usr/bin/env python3
"""Build-time self check (runs inside `docker build`, no network to the LLM).

1. openJiuwen API surface used by the harness exists and constructs offline.
2. The harness solves the bundled sample tasks with zero LLM calls.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
os.chdir(tempfile.mkdtemp())

from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig  # noqa: E402
from openjiuwen.core.foundation.tool import tool  # noqa: E402

cfg = ModelClientConfig(client_provider="OpenAI", api_base="http://127.0.0.1:9/v1",
                        api_key="x", verify_ssl=False, timeout=5.0)
m = Model(cfg, ModelRequestConfig(model="qwen3.8-27b-noreason", temperature=0.0))
assert hasattr(m, "invoke")


def read_file(path: str) -> str:
    """Read a file."""
    return path


lf = tool(read_file, name="read_file", description="Read a file.")
info = lf.card.tool_info()
assert info.name == "read_file", info
print("openJiuwen API ok:", type(m).__name__, info.name)
if "--api-only" in sys.argv[1:]:
    sys.exit(0)

sys.path.insert(0, str(APP))
from harness.sandbox import run_suite

src = APP / "samples"
work = Path(tempfile.mkdtemp()) / "tasks"
shutil.copytree(src, work)
expected = {}
for spec in work.glob("*/task.json"):
    task = json.loads(spec.read_text(encoding="utf-8"))
    expected[spec.parent.name] = task.pop("expected", "")
    spec.write_text(json.dumps(task), encoding="utf-8")
env = {k: v for k, v in os.environ.items() if k not in {"LLM_BASE_URL", "LLM_API_KEY"}}
p = subprocess.run([sys.executable, str(APP / "run_agent.py"), "--tasks-dir", str(work)],
                   env=env, capture_output=True, text=True, timeout=300)
print(p.stderr[-1500:])
if p.returncode != 0:
    print(f"harness exited with code {p.returncode}")
    sys.exit(1)
bad = []
for tj in sorted(work.glob("*/task.json")):
    t = json.loads(tj.read_text(encoding="utf-8"))
    ans_f = tj.parent / "answer.txt"
    got = ans_f.read_text(encoding="utf-8").strip() if ans_f.exists() else None
    exp = str(expected[tj.parent.name]).strip()
    if t.get("check") == "unittest":
        ws = tj.parent / "workspace"
        tests = sorted(ws.glob("test_*.py"))
        ok = bool(tests) and run_suite(ws, tests[0])[0]
    else:
        ok = got == exp
    if not ok:
        bad.append((tj.parent.name, exp, got))
total = len(list(work.glob("*/task.json")))
print(f"samples correct: {total - len(bad)}/{total}")
for b in bad:
    print("  wrong:", b[0])
if bad:
    sys.exit(1)
shutil.rmtree(work.parent, ignore_errors=True)
print("selfcheck passed")
