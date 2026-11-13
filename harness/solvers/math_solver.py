"""Deterministic solver for word-problem arithmetic.

All-or-nothing: every sentence of the problem must be understood, otherwise
we return None and the LLM fallback takes over.  Never guesses.
"""
from __future__ import annotations

import re
from fractions import Fraction

NUM = r"(\d[\d,]*(?:\.\d+)?)"
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1,
           "once": 1, "twice": 2, "thrice": 3}
MULT_WORDS = {"doubled": 2, "tripled": 3, "quadrupled": 4, "quintupled": 5}

# sentences that carry no operation
_NOISE = re.compile(r"^(compute|use|work only|when you are done|write only|for example|"
                    r"calculate|show|give|answer|note|round)", re.I)


def _n(s: str) -> Fraction:
    s = s.replace(",", "")
    if s.lower() in WORDNUM:
        return Fraction(WORDNUM[s.lower()])
    return Fraction(s)


def _split_sentences(text: str) -> list[str]:
    # protect decimals and "e.g."
    t = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text)
    t = t.replace("e.g.", "eg").replace("i.e.", "ie")
    parts = re.split(r"(?<=[.?!])\s+", t)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def _floor(x: Fraction) -> Fraction:
    return Fraction(x.numerator // x.denominator)


def _round_mode(s: str) -> str | None:
    s = s.lower()
    if "rounded down" in s or "round down" in s or "floor" in s:
        return "down"
    if "rounded up" in s or "round up" in s or "ceil" in s:
        return "up"
    if "nearest" in s or re.search(r"\brounded\b", s):
        return "nearest"
    return None


def _apply_round(x: Fraction, mode: str | None) -> Fraction | None:
    if x.denominator == 1:
        return x
    if mode == "down":
        return _floor(x)
    if mode == "up":
        return -_floor(-x)
    if mode == "nearest":
        return _floor(x + Fraction(1, 2))
    return None  # non-integer without rounding rule -> unsure


W = r"(?:[a-z]+\s+){0,3}?"  # up to 3 filler words (e.g. "boxes", "of stock")


def _op(sentence: str, x: Fraction):
    """Apply one sentence to the running value; return new value or None."""
    s = sentence.strip().rstrip(".").lower()
    s = re.sub(r"^(then|next|after that|afterwards|later|finally|and)\s*,?\s*", "", s)
    s = re.sub(r"^(it|the warehouse|the store|the shop|the stock|the farm|the library|"
               r"the account|the tank|the company|she|he|they)\s+", "", s)
    rm = _round_mode(s)

    # per-day / per-week flows
    m = re.match(rf"(ships|sells|loses|uses|gives away|removes|spends|consumes|donates|"
                 rf"sends out|withdraws|pays out)\s+{NUM}\s+{W}per\s+(day|week|month|hour|"
                 rf"shift)\s+for\s+{NUM}\s+(days|weeks|months|hours|shifts|day|week|month)", s)
    if m:
        return x - _n(m.group(2)) * _n(m.group(4))
    m = re.match(rf"(receives|gets|gains|adds|buys|produces|collects|earns|deposits|"
                 rf"takes in|harvests)\s+{NUM}\s+{W}per\s+(day|week|month|hour|shift)\s+for\s+"
                 rf"{NUM}\s+(days|weeks|months|hours|shifts|day|week|month)", s)
    if m:
        return x + _n(m.group(2)) * _n(m.group(4))
    # K deliveries of N each
    m = re.match(rf"(receives|gets|takes in)\s+{NUM}\s+(deliveries|shipments|batches|"
                 rf"loads|crates|pallets|orders)\s+of\s+{NUM}\s+{W}each", s)
    if m:
        return x + _n(m.group(2)) * _n(m.group(4))
    m = re.match(rf"(ships|sends|sells|dispatches)\s+{NUM}\s+(shipments|orders|batches|"
                 rf"loads|deliveries)\s+of\s+{NUM}\s+{W}each", s)
    if m:
        return x - _n(m.group(2)) * _n(m.group(4))
    # split equally into M and keep one share
    m = re.match(rf"(?:the )?(?:stock|inventory|total|amount)?\s*(?:is )?split equally "
                 rf"(?:into|among|between)\s+{NUM}\s+\w+.*keeps one share", s)
    if m:
        r = _apply_round(x / _n(m.group(1)), rm)
        return r
    # doubled / tripled
    m = re.match(r"(?:the )?(?:stock|inventory|total|amount)?\s*(?:is )?(doubled|tripled|"
                 r"quadrupled|quintupled)\b", s)
    if m:
        return x * MULT_WORDS[m.group(1)]
    m = re.match(rf"(?:the )?(?:stock|inventory|total|amount)?\s*(?:is )?multiplied by\s+{NUM}", s)
    if m:
        return x * _n(m.group(1))
    m = re.match(r"(?:the )?(?:stock|inventory|total|amount)?\s*(?:is )?halved\b", s)
    if m:
        return _apply_round(x / 2, rm)
    m = re.match(rf"(?:the )?(?:stock|inventory|total|amount)?\s*(?:is )?divided "
                 rf"(?:equally )?by\s+{NUM}", s)
    if m:
        return _apply_round(x / _n(m.group(1)), rm)
    # percentages
    m = re.match(rf"(?:the )?(?:stock|inventory|total|amount|it)?\s*(?:is )?(increases|grows|"
                 rf"rises|increased|grew|rose)\s+by\s+{NUM}\s*(?:%|percent)", s)
    if m:
        return _apply_round(x * (100 + _n(m.group(2))) / 100, rm)
    m = re.match(rf"(?:the )?(?:stock|inventory|total|amount|it)?\s*(?:is )?(decreases|drops|"
                 rf"falls|shrinks|decreased|dropped|fell)\s+by\s+{NUM}\s*(?:%|percent)", s)
    if m:
        return _apply_round(x * (100 - _n(m.group(2))) / 100, rm)
    m = re.match(rf"(loses|sells|ships|gives away)\s+{NUM}\s*(?:%|percent)\s+of", s)
    if m:
        return _apply_round(x * (100 - _n(m.group(2))) / 100, rm)
    # plain add / subtract
    m = re.match(rf"(receives|gets|gains|adds|buys|produces|collects|earns|deposits|"
                 rf"takes in|finds|is given)\s+(?:a delivery of\s+|another\s+)?{NUM}\b", s)
    if m:
        return x + _n(m.group(2))
    m = re.match(rf"(ships|sells|loses|uses|gives away|removes|spends|consumes|donates|"
                 rf"sends out|withdraws|pays|discards|returns|throws away)\s+{NUM}\b", s)
    if m:
        return x - _n(m.group(2))
    return None


_START = [
    re.compile(rf"(?:starts|begins|started|began) (?:with|at)\s+{NUM}", re.I),
    re.compile(rf"(?:has|had|holds|contains|stores)\s+{NUM}\b", re.I),
    re.compile(rf"(?:initially|originally)\s+(?:has|had|holds|contains)?\s*{NUM}", re.I),
]


def solve(instruction: str):
    """Return (answer_str, note) or None if not fully understood."""
    text = instruction
    sentences = _split_sentences(text)
    if not sentences:
        return None
    # the question
    q_idx = next((i for i, s in enumerate(sentences) if s.endswith("?")), None)
    if q_idx is None:
        return None
    q = sentences[q_idx].lower()
    final_stock = re.fullmatch(r"how many ([a-z]+) (?:does it have|are left|remain)"
                               r"(?: (?:now|at the end))?\?", q)
    if not final_stock:
        return None
    body = sentences[:q_idx]
    if not body:
        return None
    m = None
    for pat in _START:
        m = pat.search(body[0])
        if m:
            break
    if not m:
        return None
    # the first sentence must only define the start
    x = _n(m.group(1))
    rest_first = body[0][m.end():].strip(" .")
    if rest_first.lower() != final_stock.group(1):
        return None
    steps = 0
    for s in body[1:]:
        if _NOISE.match(s.strip()):
            continue
        nx = _op(s, x)
        if nx is None:
            return None
        x = nx
        steps += 1
    if x.denominator != 1:
        return None
    # remaining sentences after the question must be boilerplate
    for s in sentences[q_idx + 1:]:
        if not _NOISE.match(s.strip()) and not s.lower().startswith(("compute", "use ")):
            # unknown extra condition after the question -> unsure
            if re.search(r"\d", s):
                return None
    return str(int(x)), f"parsed {steps} ops"
