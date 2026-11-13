"""Subprocess helper: evaluates many candidate module sources quickly.

Usage: python _mut_runner.py payload.json   (cwd = scratch copy of workspace)
Prints one JSON line.
"""
import copy
import hashlib
import io
import json
import os
import signal
import sys
import types
import unittest

try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
except Exception:  # noqa: BLE001
    pass
try:  # OOM killer must pick this child, not the harness process
    with open("/proc/self/oom_score_adj", "w") as _f:
        _f.write("1000")
except OSError:
    pass

sys.path.insert(0, os.getcwd())
sys.setrecursionlimit(3000)


class _Timeout(Exception):
    pass


def _alarm(sig, frame):
    raise _Timeout()


if hasattr(signal, "SIGALRM"):
    signal.signal(signal.SIGALRM, _alarm)
    _set_alarm = signal.alarm
else:  # Windows: no SIGALRM; the parent process enforces an overall timeout
    def _set_alarm(_seconds):
        return 0


def load_module(name, src):
    mod = types.ModuleType(name)
    mod.__file__ = os.path.join(os.getcwd(), name + ".py")
    code = compile(src, mod.__file__, "exec")
    sys.modules[name] = mod
    exec(code, mod.__dict__)
    return mod


def run_tests(test_src, test_file, tests):
    ns = {"__name__": "__mut_tests__", "__file__": os.path.join(os.getcwd(), test_file)}
    exec(compile(test_src, test_file, "exec"), ns)
    suite = unittest.TestSuite()
    cases = [v for v in ns.values() if isinstance(v, type) and issubclass(v, unittest.TestCase)]
    funcs = {k: v for k, v in ns.items() if k.startswith("test") and callable(v)
             and not isinstance(v, type)}
    wanted = set(tests or [])
    for c in cases:
        for m in unittest.TestLoader().getTestCaseNames(c):
            if not wanted or m in wanted:
                suite.addTest(c(m))
    ok = True
    if suite.countTestCases():
        r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        ok = r.wasSuccessful()
    for k, f in funcs.items():
        if wanted and k not in wanted:
            continue
        f()  # pytest style: raises on failure
    return ok


def main():
    payload = json.load(open(sys.argv[1]))
    name = payload["module"]
    cands = payload["candidates"]
    if "behaviour" in payload:
        fname = payload["behaviour"]
        inputs = payload["inputs"]
        sigs = []
        for src in cands:
            outs = []
            try:
                _set_alarm(3)
                mod = load_module(name, src)
                _set_alarm(0)
                fn = getattr(mod, fname)
                for args in inputs:
                    try:
                        _set_alarm(1)
                        outs.append(repr(fn(*copy.deepcopy(args))))
                    except _Timeout:
                        outs.append("TIMEOUT")
                    except BaseException as e:  # noqa: BLE001
                        outs.append("EXC:" + type(e).__name__)
                    finally:
                        _set_alarm(0)
            except BaseException as e:  # noqa: BLE001
                _set_alarm(0)
                outs = ["LOADFAIL:" + type(e).__name__] * len(inputs)
            outs = [o[:300] for o in outs]
            sigs.append({"sig": hashlib.md5("|".join(outs).encode()).hexdigest(), "outs": outs})
        print(json.dumps({"sigs": sigs}))
        return
    test_file = payload["test_file"]
    test_src = open(test_file).read()
    tests = payload.get("tests") or []
    res = []
    devnull = open(os.devnull, "w")
    for src in cands:
        ok = False
        old_out, old_err = sys.stdout, sys.stderr
        try:
            sys.stdout = sys.stderr = devnull
            _set_alarm(3)
            load_module(name, src)
            ok = run_tests(test_src, test_file, tests)
        except BaseException:  # noqa: BLE001
            ok = False
        finally:
            _set_alarm(0)
            sys.stdout, sys.stderr = old_out, old_err
        res.append(bool(ok))
    print(json.dumps({"pass": res}))


if __name__ == "__main__":
    main()
