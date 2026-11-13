"""Integration: the strategy executor never spends more than BUDGET (issue #3).

Spins up tools/mock_llm.py with a small budget and checks both our ledger
and the mock proxy's own ledger.  ~10-20 s.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BudgetRespected(unittest.TestCase):
    def run_with_budget(self, budget, strategy="baseline", disable_det="math,search,data_analysis,coding"):
        work = Path(tempfile.mkdtemp())
        try:
            tasks = work / "t"
            subprocess.run([sys.executable, str(ROOT / "tools/task_factory.py"), str(tasks),
                            "--n", "40", "--seed", "5"], check=True, capture_output=True)
            truth = work / "t_truth.json"
            port = _port()
            ledger = work / "mock_ledger.json"
            mock = subprocess.Popen([sys.executable, str(ROOT / "tools/mock_llm.py"), str(truth),
                                     "--port", str(port), "--budget", str(budget * 10),
                                     "--ledger", str(ledger)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # The mock indexes all generated workspaces before listening.
            # A fixed sleep(0.8) raced with startup on slower CI runners,
            # making every request fail before the server was ready.
            deadline = time.monotonic() + 20
            while True:
                if mock.poll() is not None:
                    self.fail("mock server exited before becoming ready")
                try:
                    with socket.create_connection(("127.0.0.1", port),
                                                  timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        self.fail("mock server did not listen within 20s")
                    time.sleep(0.1)
            try:
                env = dict(os.environ, LLM_BASE_URL=f"http://127.0.0.1:{port}/v1", LLM_API_KEY="x",
                           BUDGET=str(budget), HARNESS_TRACE=str(work / "trace.json"),
                           HARNESS_DISABLE_DET=disable_det)
                p = subprocess.run([sys.executable, str(ROOT / "run_agent.py"), "--tasks-dir",
                                    str(tasks), "--strategy", strategy], env=env,
                                   capture_output=True, text=True, timeout=600)
            finally:
                mock.terminate()
                mock.wait(timeout=5)
            self.assertEqual(p.returncode, 0, p.stderr[-1000:])
            tr = json.loads((work / "trace.json").read_text())
            proxy = json.loads(ledger.read_text())["spent"] if ledger.exists() else 0.0
            return tr["spent"], proxy, tr
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_small_budget_not_exceeded(self):
        budget = 2500
        ours, proxy, tr = self.run_with_budget(budget)
        self.assertLessEqual(ours, budget)
        self.assertLessEqual(proxy, budget)
        measured = sum(c["cost"] for c in tr["calls"] if c["accounting"] == "usage")
        conservative = sum(c["cost"] for c in tr["calls"] if c["accounting"] != "usage")
        self.assertAlmostEqual(measured, proxy, delta=1.0)
        self.assertAlmostEqual(ours, measured + conservative, delta=1.0)
        self.assertGreater(measured, 0, f"trace calls={tr['calls']} results={tr['results']}")
        statuses = {r["status"] for r in tr["results"].values()}
        self.assertIn("skipped", statuses)                       # budget really was binding


if __name__ == "__main__":
    unittest.main()
