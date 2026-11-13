"""Children (model code, tests, mutants) must be the OOM killer's first choice,
so a container memory limit kills a child, never the harness process."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harness import sandbox

READ = "print(open('/proc/self/oom_score_adj').read().strip())"
LINUX = sys.platform == "linux" and Path("/proc/self/oom_score_adj").exists()


@unittest.skipUnless(LINUX, "Linux /proc required")
class OomScoreTest(unittest.TestCase):
    def _child(self, isolated):
        with tempfile.TemporaryDirectory() as d:
            return sandbox._run([sandbox.PY, "-I", "-S", "-B", "-c", READ], Path(d), 10,
                                isolated, False, None, False, None)

    def test_limits_only_child(self):
        code, out = self._child(False)
        self.assertEqual((code, out), (0, "1000"))

    def test_isolated_child(self):
        # Landlock hides /proc from the child, so read its score from outside.
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.Popen([sandbox.PY, "-I", "-S", "-B", str(sandbox.LAUNCHER), "read", "", "5",
                                  sandbox.PY, "-I", "-S", "-B", "-c",
                                  "import sys; sys.stdout.write('up\\n'); sys.stdout.flush(); sys.stdin.read()"],
                                 cwd=d, env={**os.environ, "TMPDIR": d}, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
            try:
                line = p.stdout.readline().strip()
                if line != "up":
                    p.wait(5)
                    if p.returncode == 125:
                        self.skipTest("kernel without Landlock/seccomp")
                    self.fail(f"isolated child failed: {p.returncode} {p.stderr.read()}")
                score = Path(f"/proc/{p.pid}/oom_score_adj").read_text().strip()
            finally:
                p.kill()
                p.communicate()
        self.assertEqual(score, "1000")

    def test_mutant_runner(self):
        runner = Path(sandbox.__file__).parent / "solvers" / "_mut_runner.py"
        src = runner.read_text(encoding="utf-8")
        head = src[:src.index("sys.path.insert")]
        out = subprocess.run([sys.executable, "-c", head + READ], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "1000", out.stderr)


if __name__ == "__main__":
    unittest.main()
