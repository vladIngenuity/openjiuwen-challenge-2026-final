"""Trusted completion record. Console text and a zero exit are not a verdict.

This rejects early exits/stdout spoofing and basic unittest monkeypatching.
Arbitrary code shares this interpreter: frame introspection is NOT an OS trust
boundary. Hostile-code grading needs assertions in a separate trusted process.
"""
import json
import os
from pathlib import Path
import runpy
import sys
import types
import unittest

PREFIX = '__HARNESS_TEST_RESULT__'


def main():
    request = json.loads(sys.stdin.read())
    sys.stdin.close()
    os.close(0)
    sys.stdin = open(os.devnull, encoding='utf-8')
    nonce = request['nonce']
    if not isinstance(nonce, str) or len(nonce) != 32: return 1
    source = request.get('hidden_source')
    hidden = source is not None
    path = Path(sys.argv[1])
    sys.path.insert(0, str(path.parent))
    sys.path.insert(0, str(Path.cwd()))
    protected = [(owner, name, value, getattr(value, '__code__', None))
                 for owner in (unittest.TestCase, unittest.TestSuite, unittest.TextTestRunner,
                               unittest.TestLoader, unittest.TestResult)
                 for name, value in vars(owner).items() if callable(value)]

    def intact():
        return all(vars(owner).get(name) is value and getattr(value, '__code__', None) is code
                   for owner, name, value, code in protected)

    report = {'ok': False, 'tests': 0, 'skipped': 0}
    try:
        module = types.ModuleType('_harness_suite')
        sys.modules[module.__name__] = module
        if source is not None:
            compiled = compile(source, '<hidden-suite>', 'exec')
            del source
            exec(compiled, module.__dict__)
        elif not path.is_dir():
            module.__dict__.update(runpy.run_path(str(path), run_name=module.__name__))
        if intact():
            suite = (unittest.defaultTestLoader.discover(str(path))
                     if not hidden and path.is_dir()
                     else unittest.defaultTestLoader.loadTestsFromModule(module))
            result = unittest.TextTestRunner().run(suite)
            report.update(tests=result.testsRun, skipped=len(result.skipped),
                          ok=bool(intact() and result.testsRun > len(result.skipped) and result.wasSuccessful()))
    except BaseException:
        # Never print exception/test values from a private suite into public logs.
        report['ok'] = False
    print(PREFIX + nonce + ' ' + json.dumps(report, separators=(',', ':')), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__': sys.exit(main())
