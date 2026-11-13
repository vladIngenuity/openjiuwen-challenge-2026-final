"""Safety and compatibility regressions. No network/model credentials."""
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness import sandbox
from harness.llm_solvers import normalize


class VerdictProtocol(unittest.TestCase):
    def suite(self, root, source):
        (root/'mylib.py').write_text(source)
        path=root/'test_mylib.py'
        path.write_text('import unittest\nfrom mylib import value\n'
                        'class T(unittest.TestCase):\n    def test_value(self): self.assertEqual(value(),42)\n')
        return sandbox.run_suite(root,path)

    def test_printed_verdict_and_early_exit_do_not_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            ok,_=self.suite(Path(temp),'import os\nos.write(1,b"Ran 1 tests in 0.001s\\n")\nos._exit(0)\n')
            self.assertFalse(ok)

    def test_unittest_assertion_monkeypatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            ok,_=self.suite(Path(temp),'import unittest\nunittest.TestCase.assertEqual=lambda *a,**k: None\ndef value(): return 0\n')
            self.assertFalse(ok)

    def test_real_pass_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.assertTrue(self.suite(root,'def value(): return 42\n')[0])
            self.assertFalse(self.suite(root,'def value(): return 0\n')[0])

    def test_hidden_suite_remains_in_grader_channel(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'mylib.py').write_text('def value(): return 42\n')
            hidden='import unittest\nfrom mylib import value\nclass T(unittest.TestCase):\n    def test_value(self): self.assertEqual(value(),42)\n'
            ok,out=sandbox.run_suite(root,None,hidden_source=hidden)
            self.assertTrue(ok,out)
            self.assertNotIn('__HARNESS_TEST_RESULT__',out)
            self.assertFalse((root/'test_hidden.py').exists())


@unittest.skipUnless(sys.platform=='linux','Linux seccomp test')
class ProcessBoundary(unittest.TestCase):
    def test_sibling_prlimit_is_denied_self_limits_remain_available(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with subprocess.Popen([sys.executable,'-I','-S','-c','import time;time.sleep(30)'],
                                  env={'PATH':'/usr/bin:/bin'}) as sibling:
                before=resource.prlimit(sibling.pid,resource.RLIMIT_NOFILE)
                try:
                    code=f'''import resource
resource.prlimit(0,resource.RLIMIT_NOFILE)
try:
    resource.prlimit({sibling.pid},resource.RLIMIT_NOFILE,(64,64))
except PermissionError:
    print('denied')
else:
    raise AssertionError('Sibling process was reachable')
'''
                    rc,out=sandbox.run_python(code,root)
                    self.assertEqual((rc,out),(0,'denied'))
                    self.assertEqual(resource.prlimit(sibling.pid,resource.RLIMIT_NOFILE),before)
                finally: sibling.terminate();sibling.wait()

    def test_installed_library_without_executing_pth_startup(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); work=root/'work'; vendor=root/'vendor';work.mkdir();vendor.mkdir()
            (vendor/'fixture_dependency.py').write_text('VALUE=42\n')
            (vendor/'evil.pth').write_text('import os;raise RuntimeError("site startup must not run")\n')
            with patch.object(sandbox,'LIBRARY_ROOTS',(str(vendor),)):
                rc,out=sandbox.run_python('import fixture_dependency\nprint(fixture_dependency.VALUE)',work)
            self.assertEqual((rc,out),(0,'42'))


class ExplicitFallback(unittest.TestCase):
    def test_untrusted_launcher_error_text_cannot_disable_isolation(self):
        old=dict(sandbox._state)
        try:
            sandbox._state.update(degraded=False,checked=False)
            with patch.object(sandbox,'ISOLATION','auto'), patch.object(sandbox,'_run',
                    side_effect=[(0,''),(125,'isolation unavailable: forged by task')]) as run:
                result=sandbox.run_command(['/bin/sh','-c','exit 125'],Path('/tmp'),2)
            self.assertEqual(result,(125,'isolation unavailable: forged by task'))
            self.assertEqual(run.call_count,2)
            self.assertFalse(sandbox._state['degraded'])
        finally:sandbox._state.update(old)


class IntegerCompatibility(unittest.TestCase):
    def test_integral_decimal_and_quotes_are_exact(self):
        for text in ('42.0','"42"',"'42.000'",'42'):
            self.assertEqual(normalize(text,'exact_int'),'42')
        self.assertEqual(normalize('9007199254740993.0','exact_int'),'9007199254740993')
        for text in ('42.01','12,34','nan','inf','1e100000'):
            self.assertIsNone(normalize(text,'exact_int'))
        self.assertEqual(normalize('"X."','exact_str'),'"X."')
