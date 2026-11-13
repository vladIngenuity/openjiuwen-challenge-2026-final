"""Reproducible random scheduler control, never the default.

A fixed seeded permutation chooses among tasks at the same attempt count.
Prioritize first attempts, then retries, to isolate task-selection randomness
from the number-of-retries policy used by Baseline. Budget and model decisions
are identical to Baseline. This is NOT random answer guessing.
"""
from __future__ import annotations

import hashlib
import os

from ..strategy import PENDING, RunState, TaskView
from .baseline import Baseline


class RandomBaseline(Baseline):
    name = "random"

    @staticmethod
    def _seed() -> str:
        return os.environ.get("HARNESS_RANDOM_SEED", "0")

    def order(self, tasks: list[TaskView], state: RunState) -> list[str]:
        seed = self._seed()
        pending = [t for t in tasks
                   if state.status_by_task.get(t.task_id, PENDING) == PENDING]
        def key(t):
            previous = sum(1 for a in state.attempts(t.task_id)
                           if a.kind not in ("vote", "diagnose"))
            digest = hashlib.sha256(
                (seed + "\0" + t.task_id).encode("utf-8")).digest()
            return (previous, digest, t.task_id)
        pending.sort(key=key)
        return [t.task_id for t in pending]
