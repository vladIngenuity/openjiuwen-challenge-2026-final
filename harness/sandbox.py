"""Run model and test code in a private workspace with Linux isolation."""
from __future__ import annotations

import math
import json
import secrets
import sysconfig
import threading
import re
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

PY = sys.executable
LAUNCHER = Path(__file__).with_name("_isolated.py").resolve()
PYTHON_RUNNER = Path(__file__).with_name("_python_runner.py").resolve()
LIBRARY_ROOTS = tuple(sorted({sysconfig.get_path(k) for k in ("purelib", "platlib") if sysconfig.get_path(k)}))
TEST_RUNNER = Path(__file__).with_name("_test_runner.py").resolve()
SKIP = {"answer.txt", "task.json", "__pycache__", ".git"}
OUTPUT_LIMIT = 2 * 1024**2


def copy_inputs(src: Path, dst: Path, *, skip=SKIP, preserve_mode=False) -> None:
    if src.is_symlink():
        raise ValueError(f"symlink is not a workspace: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    for path in src.iterdir():
        if path.name in skip:
            continue
        mode = path.lstat().st_mode
        target = dst / path.name
        if stat.S_ISDIR(mode):
            copy_inputs(path, target, skip=skip, preserve_mode=preserve_mode)
        elif stat.S_ISREG(mode):
            shutil.copyfile(path, target)
            if preserve_mode:
                target.chmod(stat.S_IMODE(mode) & 0o777)
        else:
            raise ValueError(f"unsupported workspace entry: {path}")


def scratch_copy(ws: Path) -> Path:
    dest = Path(tempfile.mkdtemp(prefix="sbx_"))
    try:
        copy_inputs(ws, dest)
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


# HARNESS_ISOLATION:
#   auto   (explicit opt-in) Landlock + seccomp when the kernel provides them; if the
#          launcher reports "isolation unavailable" (old kernel, no libseccomp,
#          not Linux) fall back to resource limits only and say so once.  An
#          unavailable sandbox must not zero the whole run.
#   strict fail closed: no isolation -> no code execution.
#   off    resource limits only.
ISOLATION = os.environ.get("HARNESS_ISOLATION", "strict").strip().lower()
if ISOLATION not in {"auto", "strict", "off"}:
    ISOLATION = "strict"
_state = {"degraded": ISOLATION == "off" or (sys.platform != "linux" and ISOLATION != "strict"), "checked": False}
_STATE_LOCK = threading.Lock()


def isolation_mode() -> str:
    return "limits-only" if _state["degraded"] else "landlock+seccomp"


def _prefer_oom_kill():
    # Under a container memory limit the kernel OOM killer must pick this child,
    # never the harness process (that would end the whole run).  Raising the
    # score needs no privileges.
    try:
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write("1000")
    except OSError:
        pass


def _limits(cpu: int):
    def apply():
        _prefer_oom_kill()
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3,) * 2)
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2,) * 2)
        except Exception:
            pass
    return apply


def run_command(command: list[str], cwd: Path, timeout: float, *,
                writable: bool = False, helper: Path | None = None, separate_stderr: bool = False,
                stdin_text: str | None = None) -> tuple[int, str]:
    if timeout <= 0:
        return 124, "TIMEOUT"
    if sys.platform != "linux" and ISOLATION == "strict":
        return 125, "workspace code execution requires Linux isolation"
    if ISOLATION == "auto" and not _state["degraded"]:
        with _STATE_LOCK:
            if not _state["checked"]:
                # Probe only trusted code. A task can print any diagnostic and
                # exit 125; its output must never switch isolation off.
                code, out = _run([PY, "-I", "-S", "-B", "-c", "pass"], cwd,
                                 min(timeout, 5.), True, False, None, False, None)
                if code:
                    if code != 125 or "isolation unavailable" not in out: return code, out
                    _state["degraded"] = True
                    sys.stderr.write("[sandbox] trusted preflight failed; explicit auto mode uses resource limits only\n")
                _state["checked"] = True
    return _run(command, cwd, timeout, not _state["degraded"], writable, helper,
                separate_stderr, stdin_text)


def _run(command, cwd, timeout, isolated, writable, helper, separate_stderr, stdin_text):
    posix = os.name == "posix"
    command = list(command)
    if command and command[0] == PY:
        index = 1
        while index < len(command) and command[index] in {"-I", "-S", "-B"}: index += 1
        if index < len(command) and command[index] not in {"-c", "-m"}:
            command = [PY, "-I", "-S", "-B", str(PYTHON_RUNNER), *command[index:]]
    with (tempfile.TemporaryDirectory(prefix=".exec-", dir=cwd) as temp,
          tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors,
          tempfile.TemporaryFile() as input_file):
        env = {"PATH": f"{Path(PY).parent}:/usr/local/bin:/usr/bin:/bin",
               "HOME": temp, "TMPDIR": temp, "LC_ALL": "C.UTF-8", "PYTHONUTF8": "1",
               "PYTHONDONTWRITEBYTECODE": "1",
               "HARNESS_LIBRARY_ROOTS": json.dumps(list(LIBRARY_ROOTS))}
        cpu = max(1, math.ceil(timeout))
        if isolated:
            args = [PY, "-I", "-S", "-B", str(LAUNCHER), "write" if writable else "read",
                    str(helper or ""), str(cpu), *command]
        else:
            args = list(command)
            if not posix:
                env.update({k: os.environ[k] for k in ("SYSTEMROOT", "PATH", "TEMP", "TMP")
                            if k in os.environ})
                env["PATH"] = f"{Path(PY).parent}{os.pathsep}{env.get('PATH', '')}"
        if stdin_text is not None:
            input_file.write(stdin_text.encode("utf-8"))
            input_file.seek(0)
        with subprocess.Popen(args, cwd=cwd, env=env,
                              stdin=input_file if stdin_text is not None else subprocess.DEVNULL,
                              stdout=output, stderr=errors if separate_stderr else subprocess.STDOUT,
                              start_new_session=posix,
                              preexec_fn=None if isolated or not posix else _limits(cpu)) as process:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                return 124, "TIMEOUT"
            finally:
                # Also reap a background child left by a successful shell command.
                try:
                    if posix:
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except (ProcessLookupError, OSError):
                    pass
                process.wait()
            output.seek(0)
            data = output.read(OUTPUT_LIMIT + 1)
            errors.seek(0)
            err = errors.read(OUTPUT_LIMIT + 1)
            if len(data) + len(err) > OUTPUT_LIMIT:
                return 125, "output limit exceeded"
            out = data.decode("utf-8", errors="replace").strip()
            if err.strip():
                out += "\n[stderr]\n" + err.decode("utf-8", errors="replace").strip()
            return process.returncode, out


def run_python(code: str, cwd: Path, timeout: int = 20) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", dir=cwd,
                                     encoding="utf-8", delete=False) as script:
        script.write(code)
    path = Path(script.name)
    try:
        return run_command([PY, "-I", "-S", "-B", path.name], cwd, timeout,
                           writable=True, separate_stderr=True)
    finally:
        path.unlink(missing_ok=True)


def run_shell(cmd: str, cwd: Path, timeout: int = 30) -> tuple[int, str]:
    shell = ["/bin/sh", "-c", cmd] if os.name == "posix" else ["cmd", "/c", cmd]
    return run_command(shell, cwd, timeout)


def run_suite(cwd: Path, test_file: Path | None, timeout: float = 60, *,
              hidden_source: str | None = None) -> tuple[bool, str]:
    if hidden_source is None and (test_file is None or not test_file.exists()):
        return False, "test file missing"
    nonce = secrets.token_hex(16)
    request = json.dumps({"nonce": nonce, "hidden_source": hidden_source})
    code, output = run_command(
        [PY, "-I", "-S", "-B", str(TEST_RUNNER), "-" if hidden_source is not None else str(test_file)],
        cwd, timeout, helper=TEST_RUNNER, stdin_text=request,
    )
    prefix = "__HARNESS_TEST_RESULT__" + nonce + " "
    lines = output.splitlines()
    records = [line[len(prefix):] for line in lines if line.startswith(prefix)]
    visible = "\n".join(line for line in lines if not line.startswith("__HARNESS_TEST_RESULT__"))
    if code != 0 or len(records) != 1: return False, visible
    try:
        result = json.loads(records[0])
        valid = (result.get("ok") is True and type(result.get("tests")) is int
                 and type(result.get("skipped")) is int
                 and 0 <= result["skipped"] < result["tests"])
        return valid, visible
    except (ValueError, TypeError):
        return False, visible
