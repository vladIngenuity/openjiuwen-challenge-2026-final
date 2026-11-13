"""Deterministic knowledge-base question answering.

KB format observed: one markdown file per entity:
    # Entity Name
    Key: Value
Values may reference other entities by name.  We build a graph and answer
questions by traversing relation chains named in the question.  Relation
vocabulary is taken from the KB itself (its keys) plus synonyms, so new keys
work without code changes.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path

SYNONYMS = {
    "born": ["born", "birth", "birthday", "year of birth", "birth year"],
    "employer": ["employer", "employs", "employed", "works for", "work for", "works at",
                 "work at", "working at", "working for"],
    "mentor": ["mentor", "mentored", "mentors", "advisor", "adviser", "supervisor"],
    "headquarters": ["headquarters", "headquartered", "hq", "based", "head office"],
    "founded": ["founded", "founding", "established", "foundation year", "founded in"],
    "city": ["city", "located", "lives", "live"],
    "spouse": ["spouse", "married", "husband", "wife"],
    "university": ["university", "studied", "alma mater", "graduated"],
    "ceo": ["ceo", "chief executive", "runs", "led by", "leads"],
    "industry": ["industry", "sector"],
}
# answer-type hints:  wh-phrase -> set of keys whose values fit
YEAR_KEYS_HINT = ("born", "founded", "year", "established")


def parse_kb(kb_dir: Path):
    ents: dict[str, dict] = {}
    for f in sorted(kb_dir.rglob("*")):
        if not f.is_file() or f.is_symlink() or f.suffix.lower() not in (".md", ".txt", ""):
            continue
        try:
            with f.open(encoding="utf-8", errors="replace") as source:
                text = source.read(64_000)
        except OSError:
            continue
        name = None
        attrs: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#") and name is None:
                name = line.lstrip("#").strip()
                continue
            m = re.match(r"^[-*]?\s*\**([A-Za-z][\w /'-]*?)\**\s*:\s*(.+)$", line)
            if m:
                attrs[m.group(1).strip().lower()] = m.group(2).strip()
        if name is None:
            name = f.stem.split("_", 1)[-1].replace("_", " ").title()
        ents[name.lower()] = {"name": name, "attrs": attrs, "file": f, "text": text}
    return ents


def _key_patterns(keys: set[str]) -> dict[str, list[str]]:
    pats: dict[str, list[str]] = {}
    for k in keys:
        words = {k}
        for base, syns in SYNONYMS.items():
            if base == k or base in k or k in base:
                words.update(syns)
        pats[k] = sorted(words, key=len, reverse=True)
    return pats


def _find_entities(q: str, ents: dict):
    ql = q.lower()
    found = []
    for key, e in ents.items():
        for m in re.finditer(r"\b" + re.escape(key) + r"\b", ql):
            found.append((m.start(), m.end(), key))
    # drop entities nested inside longer matches
    found.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    res = []
    last_end = -1
    for s, e, k in found:
        if s >= last_end:
            res.append((s, e, k))
            last_end = e
    return res


def _unknown_names(q: str, ents: dict) -> list[str]:
    """Capitalised multi-word names in the question that are not in the KB."""
    names = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", q)
    out = []
    for n in names:
        n2 = re.sub(r"^(In|Which|What|Who|Where|When|How|The|Is|Does|Did)\s+", "", n)
        if " " not in n2:
            continue
        if n2.lower() not in ents and not any(n2.lower() in k for k in ents):
            out.append(n2)
    return out


def _answer_type(q: str) -> str | None:
    ql = q.lower()
    if re.search(r"\bwhich year\b|\bwhat year\b|\bin which year\b|\bwhen\b", ql):
        return "year"
    if re.search(r"\bwhich city\b|\bwhat city\b|\bwhere\b|\bin which city\b", ql):
        return "city"
    if re.search(r"\bwho\b|\bwhich person\b|\bwhose\b|\bwhat is the name\b", ql):
        return "entity"
    if re.search(r"\bwhich company\b|\bwhat company\b|\bwhich organi[sz]ation\b", ql):
        return "entity"
    return None


def _value_fits(val: str, atype: str | None, ents: dict) -> bool:
    if atype is None:
        return True
    if atype == "year":
        return bool(re.fullmatch(r"\d{3,4}", val.strip()))
    if atype == "city":
        return not re.fullmatch(r"\d+", val.strip()) and val.lower() not in ents
    if atype == "entity":
        return val.lower() in ents
    return True


def solve(instruction: str, ws: Path):
    """Return ('answer', value, note) | ('infeasible', None, note) | None."""
    m = re.search(r"([\w./-]+)/\s*contains", instruction)
    kb_dir = ws / (m.group(1).strip("/") if m else "kb")
    if not kb_dir.resolve().is_relative_to(ws.resolve()) or not kb_dir.is_dir():
        kb_dir = ws
    ents = parse_kb(kb_dir)
    if not ents:
        return None
    # isolate the question sentence
    qs = [s for s in re.split(r"(?<=[.?!])\s+", instruction) if s.strip().endswith("?")]
    if len(qs) != 1:
        return None
    q = qs[0]
    found = _find_entities(q, ents)
    unknown = _unknown_names(q, ents)
    if not found:
        if unknown:
            return ("infeasible", None, f"entity not in KB: {unknown}")
        return None
    if len(found) != 1 or unknown:
        return None  # multi-entity / comparative questions -> LLM
    s0, e0, start = found[0]
    keys = set()
    for e in ents.values():
        keys.update(e["attrs"].keys())
    pats = _key_patterns(keys)
    # relation mentions in the question, outside the entity name span
    ql = q.lower()
    masked = ql[:s0] + " " * (e0 - s0) + ql[e0:]
    rels: list[tuple[int, str]] = []
    taken = [False] * len(masked)
    for k, words in pats.items():
        for w in words:
            for mm in re.finditer(r"\b" + re.escape(w) + r"\b", masked):
                if any(taken[mm.start():mm.end()]):
                    continue
                for i in range(mm.start(), mm.end()):
                    taken[i] = True
                rels.append((mm.start(), k))
    rels.sort()
    rel_keys = [k for _, k in rels]
    if not rel_keys or len(rel_keys) > 4:
        return None
    # inverse questions ("who is mentored by X", "who works at X") -> LLM
    if re.search(r"\b(mentored by|employed by|works? (at|for)|who (works|work)|"
                 r"how many|list|all)\b", ql) and _answer_type(q) == "entity":
        return None
    atype = _answer_type(q)
    answers = set()
    broken = []
    for perm in set(itertools.permutations(rel_keys)):
        cur = start
        ok = True
        for i, k in enumerate(perm):
            e = ents.get(cur)
            if e is None or k not in e["attrs"]:
                ok = False
                broken.append((perm, i, cur, k))
                break
            val = e["attrs"][k]
            if i < len(perm) - 1:
                cur = val.lower()
                if cur not in ents:
                    ok = False
                    broken.append((perm, i, cur, "<missing entity>"))
                    break
            else:
                if _value_fits(val, atype, ents):
                    answers.add(val.strip())
                else:
                    ok = False
        _ = ok
    if len(answers) == 1:
        return ("answer", answers.pop(), f"chain {rel_keys} from {start}")
    if not answers and len(set(rel_keys)) == len(rel_keys) and len(rel_keys) <= 2:
        # every ordering broke on missing data -> likely infeasible, but only
        # claim it when the natural-order chain broke on a missing link/attr
        natural = tuple(reversed(rel_keys)) if re.search(r"'s\b", ql) else tuple(rel_keys)
        for perm, i, cur, k in broken:
            if perm in (natural, tuple(rel_keys)) and (k == "<missing entity>" or cur in ents):
                return ("maybe_infeasible", None, f"chain broken at {cur}.{k}")
    return None


def retrieve_context(instruction: str, ws: Path, limit_chars: int = 3500) -> str:
    """Small relevant subset of the KB for the LLM fallback (one/two hops)."""
    m = re.search(r"([\w./-]+)/\s*contains", instruction)
    kb_dir = ws / (m.group(1).strip("/") if m else "kb")
    if not kb_dir.resolve().is_relative_to(ws.resolve()) or not kb_dir.is_dir():
        kb_dir = ws
    ents = parse_kb(kb_dir)
    found = [k for _, _, k in _find_entities(instruction, ents)]
    words = set(w.lower() for w in re.findall(r"[A-Z][a-z]{2,}", instruction))
    chosen: list[str] = []

    def add(k):
        if k in ents and k not in chosen:
            chosen.append(k)

    for k in found:
        add(k)
    for _hop in range(2):
        for k in list(chosen):
            for v in ents[k]["attrs"].values():
                add(v.lower())
    # inverse references
    for k, e in ents.items():
        if any(f in e["text"].lower() for f in found):
            add(k)
    if not chosen:
        for k, e in ents.items():
            if any(w in e["text"].lower() for w in words):
                add(k)
    suffixes = {"", ".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".log", ".ini"}
    preferred = [ents[k]["file"] for k in chosen]
    paths = dict.fromkeys(preferred + sorted(ws.rglob("*")))
    parts = []
    remaining = limit_chars
    for path in paths:
        if (path.is_symlink() or not path.is_file() or path.suffix.lower() not in suffixes
                or path.name in {"task.json", "answer.txt"}):
            continue
        header = f"--- {path.relative_to(ws)}\n"
        if remaining <= len(header) + 2:
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as source:
                text = source.read(remaining - len(header))
        except OSError:
            continue
        text = text.strip()
        if not text or "\0" in text:
            continue
        block = header + text[:remaining - len(header) - 1] + "\n"
        parts.append(block)
        remaining -= len(block)
    return "".join(parts)
