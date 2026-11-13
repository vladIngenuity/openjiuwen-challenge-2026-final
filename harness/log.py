import sys
import time

_T0 = time.monotonic()


def log(msg: str) -> None:
    sys.stderr.write(f"[{time.monotonic() - _T0:7.1f}s] {msg}\n")
    sys.stderr.flush()


def elapsed() -> float:
    return time.monotonic() - _T0
