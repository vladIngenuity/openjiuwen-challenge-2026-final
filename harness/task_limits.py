"""Shared configuration for aggregate per-task LLM spending.

The cap is in contest units (output + input/10).  A fixed ceiling is a
safety policy, not proof that 1500 is optimal for expensive tasks.
Override HARNESS_TASK_CAP for controlled evaluations of larger tasks.
"""
from __future__ import annotations

import math
import os


def positive_env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default
    return value if math.isfinite(value) and value > 0 else default


TASK_CAP = positive_env_float("HARNESS_TASK_CAP", 1500.0)
