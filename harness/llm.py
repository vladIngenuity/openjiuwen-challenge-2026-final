"""LLM access through openJiuwen with strict budget accounting.

Primary path: openjiuwen.core.foundation.llm.Model (OpenAI-compatible client).
A raw HTTP fallback is allowed only if SDK construction failed before invoke.
Any ambiguous dispatch retains its reservation and halts the ledger. No automatic
retry or cross-model fallback is performed after an unknown result.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import os
import re
import time
import urllib.error
import uuid
from typing import Any
from pathlib import Path
import math

from .budget import BudgetLedger, estimate_tokens
from .log import log


class Usage(tuple):
    """Measured token counts and the provider's completion reason."""

    def __new__(cls, input_tokens, output_tokens, reasoning_tokens, finish_reason=""):
        result = super().__new__(cls, (input_tokens, output_tokens, reasoning_tokens))
        result.finish_reason = finish_reason
        return result

MODEL_FAST = "qwen3.8-27b-noreason"        # default: dense 27B, no thinking
MODEL_FAST_ALT = "qwen3.6-35b-a3b-noreason"
MODEL_REASON = "qwen3.8-27b"               # escalation only, capped max_tokens
MODEL_REASON_ALT = "qwen3.6-35b-a3b"
ALL_MODELS = [MODEL_FAST, MODEL_FAST_ALT, MODEL_REASON, MODEL_REASON_ALT]
# if a model is unavailable (403/404), use the closest one instead
FALLBACKS = {MODEL_FAST: [MODEL_FAST_ALT], MODEL_FAST_ALT: [MODEL_FAST],
             MODEL_REASON: [MODEL_REASON_ALT, MODEL_FAST], MODEL_REASON_ALT: [MODEL_REASON, MODEL_FAST_ALT]}

_BUDGET_ERR = re.compile(r"budget|quota|exhaust|insufficient (?:funds|balance|credit)|\b402\b|payment required|token limit reached", re.I)


# Per-scope spending cap (one attempt, one vote, one diagnosis).  Set by the
# Executor with ``cap_scope``; every call inside the scope is clamped so that
# the scope's reservations never exceed its cap.
_SCOPE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("llm_cap_scope",
                                                                   default=None)
MIN_CALL_OUTPUT = 30


@contextlib.contextmanager
def cap_scope(cap: float):
    """Limit the total cost of LLM calls made inside this block to ``cap`` units."""
    if not math.isfinite(cap) or cap < 0:
        raise ValueError("scope cap must be finite and nonnegative")
    sc = {"cap": float(cap), "spent": 0.0, "pending": 0.0, "parent": _SCOPE.get()}
    tok = _SCOPE.set(sc)
    try:
        yield sc
    finally:
        _SCOPE.reset(tok)


class LLMUnavailable(Exception):
    pass


class RateLimiter:
    """Space physical request starts across all models of one harness run."""

    def __init__(self, rpm: int = 30):
        if not isinstance(rpm, int) or rpm < 1:
            raise ValueError("LLM_RPM must be a positive integer")
        self.interval = 60.0 / rpm
        self.lock = asyncio.Lock()
        self.next_request = 0.0

    async def acquire(self, time_left):
        async with self.lock:
            wait = max(0.0, self.next_request - time.monotonic())
            if time_left() <= wait:
                raise LLMUnavailable("deadline")
            if wait:
                await asyncio.sleep(wait)
            self.next_request = time.monotonic() + self.interval

    def complete(self):
        # With the default one in-flight request, this also keeps a full
        # interval after SDK setup and provider response, not just acquire().
        self.next_request = max(self.next_request, time.monotonic() + self.interval)


class ProxyError(Exception):
    """HTTP error of the raw transport with the provider's error code kept, so
    that e.g. 429 insufficient_quota is not retried as a rate limit and
    400 model_not_found switches the model."""

    def __init__(self, status: int, body: str, headers=None):
        self.status_code = status
        self.headers = headers
        code = message = ""
        try:
            err = json.loads(body).get("error") or {}
            if isinstance(err, dict):
                code = str(err.get("code") or err.get("type") or "")
                message = str(err.get("message") or "")
            else:
                message = str(err)
        except (ValueError, AttributeError):
            message = body[:300]
        self.code = code
        super().__init__(f"HTTP error {status} {code} {message}"[:500])


class _SetupError(Exception):
    """The SDK failed before a request could be sent."""


def classify_error(e) -> str:
    """quota: shared budget exhausted -> stop everything
    model: this model is not available (403/404 or unknown model) -> switch model
    transient: 408/409/425/429/5xx/connection problems -> back off and retry
    fatal: other 4xx (bad request, auth) -> do not retry this request"""
    if e is None:
        return "transient"
    text = str(e)
    code = str(getattr(e, "code", "") or "").lower()
    if _BUDGET_ERR.search(text) or code in {"insufficient_quota", "billing_hard_limit_reached"}:
        return "quota"
    status = _http_status(e)
    if code in {"model_not_found", "model_not_available", "invalid_model"}:
        return "model"
    if status is None:
        return "transient"
    if status in (403, 404) or (status == 400 and re.search(r"model", text, re.I)
                                and re.search(r"not (found|exist|available|support)", text, re.I)):
        return "model"
    if status in (408, 409, 425, 429) or status >= 500:
        return "transient"
    return "fatal"


def _http_status(e) -> int | None:
    if e is None:
        return None
    if isinstance(e, urllib.error.HTTPError):
        return e.code
    response = getattr(e, "response", None)
    if isinstance(getattr(response, "status_code", None), int):
        return response.status_code
    for attr in ("status_code", "status", "code"):
        v = getattr(e, attr, None)
        if isinstance(v, int) and 100 <= v < 600:
            return v
    m = re.search(r"(?:status(?:_code)?|error code|http error)\D{0,6}([1-5]\d\d)\b", str(e), re.I)
    return int(m.group(1)) if m else None


class LLM:
    def __init__(self, ledger: BudgetLedger, max_concurrency: int | None = None, *,
                 time_left=None):
        if max_concurrency is None:
            # One in-flight request avoids a short burst on the shared provider key.
            try:
                max_concurrency = max(1, int(os.environ.get("LLM_CONCURRENCY", "1")))
            except ValueError:
                max_concurrency = 1
        try:
            rpm = int(os.environ.get("LLM_RPM", "30"))
        except ValueError as error:
            raise ValueError("LLM_RPM must be a positive integer") from error
        self.ledger = ledger
        self.base = (os.environ.get("LLM_BASE_URL") or "").strip().rstrip("/").removesuffix("/chat/completions")
        self.key = os.environ.get("LLM_API_KEY") or ""
        self.sem = asyncio.Semaphore(max_concurrency)
        self.rate_limiter = RateLimiter(rpm)
        self.enabled = bool(self.base)
        self._oj_models: dict[str, Any] = {}
        self._oj_ok = True
        self.time_left = time_left or (lambda: float("inf"))
        self.bad_models: set[str] = set()
        self.pinned_model = os.environ.get("HARNESS_PIN_MODEL", "").strip()
        if self.pinned_model and self.pinned_model not in ALL_MODELS:
            raise ValueError("HARNESS_PIN_MODEL must be one of " + repr(ALL_MODELS))
        self.backend_used = "none"

    # ------------------------------------------------------------ openJiuwen
    def _oj_model(self, name: str):
        if name in self._oj_models:
            return self._oj_models[name]
        from openjiuwen.core.foundation.llm import (Model, ModelClientConfig,
                                                    ModelRequestConfig)
        client_cfg = ModelClientConfig(
            client_provider="OpenAI",
            api_base=self.base,
            api_key=self.key or "EMPTY",
            verify_ssl=self.base.startswith("https"),
            timeout=180.0, max_retries=0,
        )
        req_cfg = ModelRequestConfig(model=name, temperature=0.0)
        m = Model(client_cfg, req_cfg)
        self._oj_models[name] = m
        return m

    async def _call_oj(self, model: str, messages, max_tokens, tools):
        try:
            m = self._oj_model(model)
        except Exception as error:
            raise _SetupError() from error
        resp = await m.invoke(messages, tools=tools or None, model=model,
                              temperature=0.0, max_tokens=max_tokens)
        u = resp.usage_metadata
        tool_calls = []
        for tc in (resp.tool_calls or []):
            tool_calls.append({"id": tc.id or f"call_{len(tool_calls)}",
                               "name": tc.name,
                               "arguments": (tc.arguments if isinstance(tc.arguments, str)
                                             else json.dumps(tc.arguments or {}))})
        content = resp.content if isinstance(resp.content, str) else json.dumps(resp.content)
        usage = None
        if u is not None and (u.input_tokens or u.output_tokens):
            usage = Usage(u.input_tokens, u.output_tokens, u.reasoning_tokens or 0,
                          getattr(resp, "finish_reason", "") or "")
        return content or "", tool_calls, usage, resp.reasoning_content or ""

    # ---------------------------------------------------------------- raw HTTP
    async def _call_raw(self, model, messages, max_tokens, tools):
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.0}
        if tools:
            body["tools"] = tools
        try:
            import httpx
        except ImportError:      # stdlib safety net: never depend on one HTTP client
            data = await asyncio.to_thread(self._post_urllib, body)
        else:
            async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
                response = await client.post(
                    self.base + "/chat/completions", json=body, timeout=180,
                    headers={"Authorization": f"Bearer {self.key}"},
                )
                if response.status_code >= 400:
                    raise ProxyError(response.status_code, response.text, response.headers)
                data = response.json()
        msg = data["choices"][0]["message"]
        tool_calls = [
            {"id": tc.get("id") or f"call_{i}", "name": tc["function"].get("name", ""),
             "arguments": tc["function"].get("arguments") or "{}"}
            for i, tc in enumerate(msg.get("tool_calls") or [])
        ]
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        return (msg.get("content") or "", tool_calls,
                Usage(usage.get("prompt_tokens"), usage.get("completion_tokens"),
                      details.get("reasoning_tokens") or 0,
                      data["choices"][0].get("finish_reason", "") or ""),
                msg.get("reasoning_content") or msg.get("reasoning") or "")

    def _post_urllib(self, body: dict) -> dict:
        import urllib.request
        req = urllib.request.Request(
            self.base + "/chat/completions", data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProxyError(e.code, e.read().decode("utf-8", "replace"), e.headers) from None

    # ------------------------------------------------------------------ public
    def _fallback_model(self, model: str) -> str | None:
        chain = FALLBACKS.get(model, [])
        for m in chain:
            if m not in self.bad_models:
                return m
        return None

    async def chat(self, messages: list[dict], *, model: str = MODEL_FAST,
                   max_tokens: int = 400, tools: list[dict] | None = None,
                   tag: str = "") -> dict:
        """Return one answer and the total cost of its transport attempts."""
        if self.pinned_model:
            model = self.pinned_model  # physical-call boundary, including votes and tool calls
        prompt = json.dumps([messages, tools], ensure_ascii=False)
        estimated_input = estimate_tokens(prompt)
        schema = [{"type": "function", "function": t} for t in tools] if tools else None
        transport = "openjiuwen" if self._oj_ok else "raw"
        requested = max_tokens if "noreason" in model else min(2500, max(max_tokens, 1500))
        result, error, debit = await self._request(
            transport, messages, model, requested, schema, tag, estimated_input)
        if isinstance(error, _SetupError):
            # The constructor failed before invoke. This is the only safe fallback.
            self._oj_ok = False
            cause = error.__cause__
            self.setup_error_type = type(cause).__name__ if cause else "unknown"
            log(f"[llm] SDK setup failed ({self.setup_error_type}); using HTTP transport")
            transport = "raw"
            result, error, debit = await self._request(
                transport, messages, model, requested, schema, tag, estimated_input)
        if result is not None:
            self.backend_used = transport
            return {"content": result[0], "tool_calls": result[1], "cost": debit,
                    "model": model, "finish_reason": getattr(result[2], "finish_reason", "")}
        status = _http_status(error)
        # Even a 503 is an accounting halt, not proof of permanent service failure.
        # No sleep, alternate model, or second transport after an ambiguous send.
        raise LLMUnavailable(self.ledger.halt_reason or
                             (f"proxy error (HTTP {status})" if status else "proxy error"))

    @staticmethod
    def _scopes(scope):
        while scope is not None:
            yield scope
            scope = scope.get("parent")

    def _journal(self, event, meta):
        path = os.environ.get("HARNESS_REQUEST_JOURNAL")
        if not path:
            return
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, **meta}, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _commit(self, scope, ticket, usage, meta):
        cost = self.ledger.commit(ticket, *usage, meta=meta)
        for sc in self._scopes(scope):
            sc["pending"] = max(0.0, sc["pending"] - ticket.amount)
            sc["spent"] += cost
        self._journal("settled", self.ledger.log[-1])
        return cost

    def _commit_uncertain(self, scope, ticket, meta):
        cost = self.ledger.commit_uncertain(ticket, meta)
        for sc in self._scopes(scope):
            sc["pending"] = max(0.0, sc["pending"] - ticket.amount)
            sc["spent"] += cost
        self._journal("settled", self.ledger.log[-1])
        return cost

    async def _request(self, transport, messages, model, requested, tools, tag, estimated_input):
        # Wait for a transport slot before reserving. Cancellation in the queue
        # leaves neither a charge nor a reservation.
        async with self.sem:
            if self.time_left() <= 0:
                raise LLMUnavailable("deadline")
            if not self.enabled or self.ledger.dead:
                raise LLMUnavailable(self.ledger.halt_reason or "proxy unavailable")
            # No ticket exists while waiting. A cancelled/deadline-expired waiter
            # cannot consume budget or create an uncertain provider charge.
            await self.rate_limiter.acquire(self.time_left)
            if self.time_left() <= 0:
                raise LLMUnavailable("deadline")
            if self.ledger.dead:
                raise LLMUnavailable(self.ledger.halt_reason or "proxy unavailable")
            scope = _SCOPE.get()
            input_cost = estimated_input / 10
            output = requested
            for sc in self._scopes(scope):
                left = sc["cap"] - sc["spent"] - sc["pending"] - input_cost
                if left < MIN_CALL_OUTPUT:
                    raise LLMUnavailable("cap")
                output = min(output, int(left))
            reserve = input_cost + output
            ticket = self.ledger.try_reserve(reserve)
            if ticket is None:
                raise LLMUnavailable("budget")
            for sc in self._scopes(scope):
                sc["pending"] += reserve
            meta = {"request_id": uuid.uuid4().hex, "tag": tag,
                    "model": model, "transport": transport, "reserved": reserve,
                    "effective_max_tokens": output, "estimated_input": estimated_input}
            start = time.monotonic()
            call = self._call_oj if transport == "openjiuwen" else self._call_raw
            try:
                self._journal("dispatch", meta)
            except OSError:
                self.ledger.release(ticket)
                for sc in self._scopes(scope):
                    sc["pending"] -= reserve
                raise
            try:
                async with asyncio.timeout(min(180, self.time_left())):
                    result = await call(model, messages, output, tools)
            except _SetupError as error:
                self.ledger.release(ticket)
                for sc in self._scopes(scope):
                    sc["pending"] = max(0.0, sc["pending"] - reserve)
                self._journal("not_sent", meta)
                return None, error, 0.0
            except asyncio.CancelledError:
                self._commit_uncertain(scope, ticket,
                    {**meta, "error": "cancelled",
                     "sec": round(time.monotonic() - start, 2)})
                raise
            except Exception as error:
                status = _http_status(error)
                # Fail closed: a transport/proxy error can occur after the server
                # started generating. Reserve remains charged; NEVER auto-retry.
                debit = self._commit_uncertain(scope, ticket,
                    {**meta, "error": classify_error(error), "http_status": status,
                     "sec": round(time.monotonic() - start, 2)})
                return None, error, debit
            finally:
                self.rate_limiter.complete()

            valid_response = isinstance(result, tuple) and len(result) == 4
            usage = result[2] if valid_response else None
            measured = (isinstance(usage, (tuple, list)) and len(usage) == 3
                        and all(type(v) is int and v >= 0 for v in usage) and usage[0] > 0
                        and (not self.ledger.reasoning_in_output or usage[2] <= usage[1]))
            if not measured:
                debit = self._commit_uncertain(scope, ticket,
                    {**meta, "error": "missing or inconsistent usage",
                     "sec": round(time.monotonic() - start, 2)})
                return None, ValueError("unknown provider usage"), debit
            if usage[1] + (0 if self.ledger.reasoning_in_output else usage[2]) > output:
                self.ledger.mark_dead("provider_exceeded_output_cap")
                meta["error"] = "provider exceeded output cap"
            debit = self._commit(scope, ticket, usage,
                                 {**meta, "accounting": "usage",
                                  "finish_reason": getattr(usage, "finish_reason", ""),
                                  "sec": round(time.monotonic() - start, 2)})
            if self.ledger.dead:
                return None, ValueError("unsafe provider usage; ledger halted"), debit
            if not valid_response:
                return None, ValueError("invalid proxy response"), debit
            return result, None, debit
