"""Opt-in hypotheses; real-Qwen reward superiority has NOT been established.

Keep the Baseline ordering and budgets so the first ablation changes only voting.
The bounded candidate then removes blind scheduler retries. Local code execution
may justify one repair carrying the actual failed code and error as feedback.
"""
from .fixed_models import AlwaysReason


class AlwaysReasonNoVote(AlwaysReason):
    name = "always_reason_no_vote"

    def should_verify(self, task, result, state):
        return False


class ReasonFirstBounded(AlwaysReasonNoVote):
    name = "reason_first_bounded"
    execution_repairs = 1
    max_tool_steps = 6
    stop_repeated_tools = True

    def should_escalate(self, task, result, state):
        return False
