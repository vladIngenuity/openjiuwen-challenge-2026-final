"""Thread-safe token ledger with unique, one-shot reservation tickets.

Contest units = output_tokens + 0.1 * input_tokens. For uncertain transport
outcomes, debit the FULL reserved maximum and stop any additional requests.
"""
from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass
from uuid import uuid4


def cost_of(input_tokens: int, output_tokens: int, reasoning_tokens: int = 0, *,
            reasoning_in_output: bool = True) -> float:
    billed = output_tokens if reasoning_in_output else output_tokens + reasoning_tokens
    return (10 * billed + input_tokens) / 10


def estimate_tokens(text: str) -> int:
    """Conservative heuristic, NOT a formal upper bound on provider tokenization."""
    if not text:
        return 64
    return max(64, len(text.encode("utf-8")) + 32)


@dataclass(frozen=True)
class Ticket:
    id: str
    amount: float
    owner: int


class BudgetLedger:
    def __init__(self, total: float | None = None, reserve_frac: float = 0.02):
        if total is None:
            total = float(os.environ.get("BUDGET", "100000"))
        if not math.isfinite(total) or total <= 0:
            raise ValueError("BUDGET must be positive and finite")
        self.total = float(total)
        self.reserve = min(max(300.0, total * reserve_frac), total * 0.30)
        mode = os.environ.get("HARNESS_REASONING_USAGE", "included")
        if mode not in {"included", "separate"}:
            raise ValueError("HARNESS_REASONING_USAGE must be included or separate")
        self.reasoning_in_output = mode == "included"
        self.spent = 0.0
        self.pending = 0.0
        self.calls = 0
        self.dead = False
        self.halt_reason = ""
        self._lock = threading.RLock()
        self._active: dict[str, float] = {}
        self.log: list[dict] = []

    @property
    def remaining(self) -> float:
        with self._lock:
            return self.total - self.spent - self.pending

    def usable(self) -> float:
        with self._lock:
            return self.total - self.spent - self.pending - self.reserve

    def try_reserve(self, amount: float) -> Ticket | None:
        if not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
            raise ValueError("reservation must be positive and finite")
        with self._lock:
            if self.dead or self.total - self.spent - self.pending - self.reserve + 1e-8 < amount:
                return None
            t = Ticket(uuid4().hex, float(amount), id(self))
            self._active[t.id] = t.amount
            self.pending += amount
            return t

    def _take_ticket(self, ticket: Ticket) -> float:
        if not isinstance(ticket, Ticket) or ticket.owner != id(self):
            raise ValueError("invalid reservation ticket")
        amount = self._active.pop(ticket.id, None)
        if amount is None:
            raise ValueError("reservation already settled or released")
        self.pending -= amount
        return amount

    def commit(self, ticket: Ticket, input_tokens: int, output_tokens: int,
               reasoning_tokens: int = 0, meta: dict | None = None) -> float:
        for x in (input_tokens, output_tokens, reasoning_tokens):
            if not isinstance(x, int) or isinstance(x, bool) or x < 0:
                raise ValueError("token usage must be nonnegative integers")
        cost = cost_of(input_tokens, output_tokens, reasoning_tokens,
                       reasoning_in_output=self.reasoning_in_output)
        with self._lock:
            reserved = self._take_ticket(ticket)
            if cost > reserved + 1e-8:
                self.dead = True  # unknown tokenization / provider behavior: fail closed
                self.halt_reason = "usage_exceeded_reservation"
            self.spent += cost
            self.calls += 1
            rec = {"t": round(time.time(), 2), "in": input_tokens,
                   "out": output_tokens, "reason": reasoning_tokens,
                   "cost": round(cost, 1), "spent": round(self.spent, 1),
                   "reserved": round(reserved, 1),
                   "over_reserved": cost > reserved + 1e-8}
            if meta:
                rec.update(meta)
            self.log.append(rec)
            return cost

    def commit_uncertain(self, ticket: Ticket, meta: dict | None = None) -> float:
        """Charge full reservation and stop. No retry after unknown outcome."""
        with self._lock:
            reserved = self._take_ticket(ticket)
            self.spent += reserved
            self.calls += 1
            self.dead = True
            self.halt_reason = "uncertain_usage"
            rec = {"t": round(time.time(), 2), "in": None, "out": None,
                   "reason": None, "cost": round(reserved, 1),
                   "spent": round(self.spent, 1), "reserved": round(reserved, 1),
                   "accounting": "uncertain_full_reservation"}
            if meta:
                rec.update(meta)
            self.log.append(rec)
            return reserved

    def release(self, ticket: Ticket):
        with self._lock:
            self._take_ticket(ticket)

    def mark_dead(self, reason: str = "unavailable"):
        with self._lock:
            self.dead = True
            self.halt_reason = self.halt_reason or reason
