"""Strategy registry.  Add a module here and register it in STRATEGIES."""
from __future__ import annotations

from .fixed_models import AlwaysFast, AlwaysReason
from .reason_first_bounded import AlwaysReasonNoVote, ReasonFirstBounded
from .empirical_hybrid import EmpiricalHybrid

from ..strategy import check_strategy
from .baseline import Baseline
from .marginal_action import MarginalAction
from .online_calibration import OnlineCalibration
from .random_baseline import RandomBaseline
from .ablations import MarginalNoPenalty, MarginalSoftPenalty, OnlineCostOnly
from .qwen_preflight import QwenPreflight
from .online_neural import OnlineNeural

STRATEGIES = {
    "empirical_hybrid": EmpiricalHybrid,
    "always_reason_no_vote": AlwaysReasonNoVote,
    "reason_first_bounded": ReasonFirstBounded,
    "always_fast": AlwaysFast,
    "always_reason": AlwaysReason,
    "baseline": Baseline,
    "marginal_action": MarginalAction,
    "online_calibration": OnlineCalibration,
    "random": RandomBaseline,
    "marginal_no_penalty": MarginalNoPenalty,
    "marginal_soft_penalty": MarginalSoftPenalty,
    "online_cost_only": OnlineCostOnly,
    "qwen_preflight": QwenPreflight,
    "online_mlp": OnlineNeural,
}


def get(name: str):
    if name not in STRATEGIES:
        raise SystemExit(f"unknown strategy {name!r}; known: {', '.join(sorted(STRATEGIES))}")
    s = STRATEGIES[name]()
    problems = check_strategy(s)
    if problems:
        raise SystemExit(f"strategy {name!r} violates the contract: {problems}")
    return s
