"""Model-pinned variants of existing Baseline; same scheduling policy.

These compare fixed-model *configurations*, not direct single-call accuracy.
All physical calls are pinned in LLM.chat() by HARNESS_PIN_MODEL.
"""
from .baseline import Baseline
from ..llm import MODEL_FAST, MODEL_REASON


class AlwaysFast(Baseline):
    name = "always_fast"
    def model_for(self, task, state, attempt):
        return MODEL_FAST


class AlwaysReason(Baseline):
    name = "always_reason"
    def model_for(self, task, state, attempt):
        return MODEL_REASON
