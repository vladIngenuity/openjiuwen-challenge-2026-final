"""Regression tests for issue #15 and the review of PR #7.

bytes inputs in the coding repair, time limits of the free phase, weak
(deletion-only) fixes held back for the model, sandbox fallback when Linux
isolation is unavailable, provider error codes of the raw transport.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import sandbox  # noqa: E402
from harness.llm import ProxyError, classify_error  # noqa: E402
from harness.solvers import coding_solver  # noqa: E402

BYTES_LIB = '''def frames(data):
    out = []
    i = 0
    while i < len(data):
        n = data[i]
        i += 1
        out.append(data[i:i + n + 1])
        i += n
    return out
'''
BYTES_TEST = '''import unittest
from mylib import frames


class T(unittest.TestCase):
    def test_two(self):
        self.assertEqual(frames(b"\\x01a\\x02bc"), [b"a", b"bc"])

    def test_empty(self):
        self.assertEqual(frames(b""), [])


if __name__ == "__main__":
    unittest.main()
'''
INSTR = "Repair frames(data) in mylib.py. Run python3 test_mylib.py; keep the tests unchanged."


def make_task(root: Path, name="coding_bytes"):
    d = root / name
    (d / "workspace").mkdir(parents=True)
    (d / "workspace" / "mylib.py").write_text(BYTES_LIB)
    (d / "workspace" / "test_mylib.py").write_text(BYTES_TEST)
    (d / "task.json").write_text(json.dumps({
        "task_id": name, "task_type": "coding", "check": "unittest", "reward": 5,
        "instruction": INSTR}))
    return d


class BytesInputs(unittest.TestCase):
    def test_repair_does_not_crash_on_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_task(Path(tmp))
            r = coding_solver.repair(INSTR, d / "workspace", max_seconds=30)
            self.assertIn(r["status"], {"fixed", "partial", "unsupported"})
            if r["status"] == "fixed":
                self.assertIn("weak", r)


class TimeLimits(unittest.TestCase):
    def test_repair_respects_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_task(Path(tmp))
            t0 = time.monotonic()
            coding_solver.repair(INSTR, d / "workspace", max_seconds=3)
            self.assertLess(time.monotonic() - t0, 12)

    def test_phase_limit_leaves_tasks_pending_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = Path(tmp) / "tasks"
            for i in range(6):
                make_task(tasks, f"coding_bytes_{i}")
            env = {k: v for k, v in os.environ.items() if k not in ("LLM_BASE_URL", "LLM_API_KEY")}
            env.update(HARNESS_DET_PHASE_SECONDS="1", HARNESS_TRACE=str(Path(tmp) / "tr.json"))
            t0 = time.monotonic()
            p = subprocess.run([sys.executable, str(ROOT / "run_agent.py"), "--tasks-dir", str(tasks)],
                               env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr[-800:])
            self.assertLess(time.monotonic() - t0, 60)
            tr = json.loads((Path(tmp) / "tr.json").read_text())
            statuses = {r["status"] for r in tr["results"].values()}
            self.assertTrue(statuses <= {"verified", "skipped"}, statuses)   # offline run is finalized
            self.assertIn("skipped", statuses)


class ModelFirstForCoding(unittest.TestCase):
    def test_free_repair_is_held_back_when_model_is_available(self):
        from unittest import mock
        from harness import pipeline
        fixed = BYTES_LIB.replace("data[i:i + n + 1]", "data[i:i + n]")
        fake = {"status": "fixed", "files": {"mylib.py": fixed}, "note": "frames: slice", "weak": False}
        with tempfile.TemporaryDirectory() as tmp:
            tasks = Path(tmp) / "tasks"
            make_task(tasks, "coding_hold")
            h = pipeline.Harness(tasks, None)
            t = h.tasks[0]
            with mock.patch.object(coding_solver, "repair", return_value=fake):
                h.llm.enabled = False
                self.assertEqual(h.deterministic(t)[0], "fixed")      # offline: use it
                h.llm.enabled = True
                r = h.deterministic(t)
            self.assertEqual(r[0], "weak_fix")                        # model goes first
            self.assertEqual(t.status, "pending")
            t.raw["_det"] = r
            self.assertTrue(h.apply_weak_fix(t))                      # fallback publishes it
            self.assertEqual(t.status, "verified")


class SandboxFallback(unittest.TestCase):
    def test_runs_without_linux_isolation(self):
        old = dict(sandbox._state)
        try:
            sandbox._state["degraded"] = True
            with tempfile.TemporaryDirectory() as tmp:
                rc, out = sandbox.run_python("print(6 * 7)", Path(tmp))
                self.assertEqual((rc, out), (0, "42"))
                self.assertEqual(sandbox.isolation_mode(), "limits-only")
        finally:
            sandbox._state.update(old)


class ProviderErrorCodes(unittest.TestCase):
    def test_quota_is_not_a_rate_limit(self):
        e = ProxyError(429, json.dumps({"error": {"code": "insufficient_quota", "message": "x"}}))
        self.assertEqual(classify_error(e), "quota")

    def test_plain_429_is_transient(self):
        e = ProxyError(429, json.dumps({"error": {"message": "too many concurrent requests"}}))
        self.assertEqual(classify_error(e), "transient")

    def test_model_not_found_switches_model(self):
        e = ProxyError(400, json.dumps({"error": {"code": "model_not_found", "message": "x"}}))
        self.assertEqual(classify_error(e), "model")


if __name__ == "__main__":
    unittest.main()
