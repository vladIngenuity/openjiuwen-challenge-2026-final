"""Task scanning and answer persistence."""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .log import log


@dataclass
class Task:
    task_id: str
    task_type: str
    instruction: str
    reward: float
    check: str
    dir: Path
    raw: dict = field(default_factory=dict)
    # filled by the pipeline
    # pending | verified | answered_unverified | infeasible_claimed | skipped | failed
    status: str = "pending"
    verify: str = "none"         # unittest | det_parse | vote | none
    answer: str | None = None
    solver: str = ""
    cost: float = 0.0
    note: str = ""
    t_start: float = 0.0
    seconds: float = 0.0

    @property
    def ws(self) -> Path:
        w = self.dir / "workspace"
        return w if w.is_dir() else self.dir


def scan(tasks_dir: Path) -> list[Task]:
    tasks: list[Task] = []
    ids = set()
    for tj in sorted(tasks_dir.glob("*/task.json")):
        if tj.is_symlink() or tj.parent.is_symlink() or (tj.parent / "workspace").is_symlink():
            log(f"refusing symlinked task: {tj.parent.name}")
            continue
        try:
            raw = json.loads(tj.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            log(f"cannot parse {tj}: {e}")
            continue
        if not isinstance(raw, dict):
            log(f"task specification is not a JSON object: {tj}")
            continue
        task_id = str(raw.get("task_id") or tj.parent.name)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", task_id) or task_id in ids:
            log(f"invalid or duplicate task ID: {task_id!r}")
            continue
        # Never let the reference answer leak into solving.
        raw.pop("expected", None)
        try:
            reward = float(raw.get("reward", 1) or 0)
        except (TypeError, ValueError):
            reward = 1.0
        if not math.isfinite(reward) or reward < 0:
            log(f"invalid reward for {task_id}")
            continue
        ids.add(task_id)
        ttype = str(raw.get("task_type") or tj.parent.name.rsplit("_", 1)[0]).lower()
        tasks.append(Task(
            task_id=task_id,
            task_type=ttype,
            instruction=str(raw.get("instruction") or ""),
            reward=reward,
            check=str(raw.get("check") or ""),
            dir=tj.parent,
            raw=raw,
        ))
    return tasks


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class AnswerStore:
    """Writes answer.txt immediately and keeps a results file up to date."""

    def __init__(self, out_path: str | None):
        self.out_path = Path(out_path) if out_path else None
        if self.out_path is not None and (self.out_path.is_dir() or str(out_path).endswith("/")):
            self.out_path = self.out_path / "results.json"
        self.results: dict[str, dict] = {}
        self._lock = threading.Lock()

    def write_answer(self, task: Task, answer: str, calls: list | None = None) -> None:
        answer = answer.strip()
        text = answer + "\n"
        _atomic_write(task.dir / "answer.txt", text)
        task.answer = answer
        self.record(task, calls)

    def record(self, task: Task, calls: list | None = None) -> None:
        import time as _t
        if task.t_start:
            task.seconds = round(_t.time() - task.t_start, 2)
        with self._lock:
            self.results[task.task_id] = {
                "task_id": task.task_id, "type": task.task_type,
                "reward": task.reward, "status": task.status,
                "answer": task.answer, "verify": task.verify, "solver": task.solver,
                "calls": calls or [], "cost_total": round(task.cost, 1),
                "seconds": task.seconds, "note": task.note[:200],
            }
            self._flush()

    def _flush(self) -> None:
        if self.out_path is None:
            return
        try:
            _atomic_write(self.out_path, json.dumps(
                {"results": list(self.results.values())}, ensure_ascii=False, indent=1))
        except OSError as e:
            log(f"cannot write results file {self.out_path}: {e}")
            raise
