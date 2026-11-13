"""Deterministic CSV analytics for recognised question templates."""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path

Q = r"['\"‘’“”]"


def load_csv(path: Path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f, delimiter="\t" if path.suffix.lower() == ".tsv" else ","))
    return rows


def find_csv(instruction: str, ws: Path) -> Path | None:
    m = re.search(r"([\w./-]+\.(?:csv|tsv))", instruction)
    if m:
        path = ws / m.group(1)
        if not path.is_symlink() and path.is_file() and path.resolve().is_relative_to(ws.resolve()):
            return path
        return None
    files = sorted(p for p in ws.rglob("*.csv") if not p.is_symlink() and p.is_file())
    return files[0] if len(files) == 1 else None


def _num(v: str):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def _parse_filters(text: str, columns: list[str]):
    """Extract filters from the question tail.  Returns (filters, leftover)."""
    filters = []
    t = text
    cols = {c.lower(): c for c in columns}
    # "product 'widget'", "region 'west'", "in the west region"
    for c_l, c in cols.items():
        for m in list(re.finditer(rf"\b{re.escape(c_l)}\s+{Q}([^'\"‘’“”]+){Q}", t)):
            filters.append(("eq", c, m.group(1)))
            t = t.replace(m.group(0), " ")
        for m in list(re.finditer(rf"\b(?:in|from|for) (?:the )?{Q}?(\w+){Q}? {re.escape(c_l)}\b", t)):
            filters.append(("eq", c, m.group(1)))
            t = t.replace(m.group(0), " ")
    # month ranges
    if "month" in cols:
        mc = cols["month"]
        m = re.search(r"\bin months? (\d+)\s*(?:through|to|-|–|and)\s*(\d+)(?: inclusive)?", t)
        if m:
            filters.append(("range", mc, int(m.group(1)), int(m.group(2))))
            t = t.replace(m.group(0), " ")
        else:
            m = re.search(r"\bin month (\d+)\b", t)
            if m:
                filters.append(("range", mc, int(m.group(1)), int(m.group(1))))
                t = t.replace(m.group(0), " ")
    return filters, t


def _apply(rows, filters):
    out = []
    for r in rows:
        ok = True
        for f in filters:
            if f[0] == "eq":
                if str(r.get(f[1], "")).strip().lower() != f[2].strip().lower():
                    ok = False
                    break
            elif f[0] == "range":
                v = _num(r.get(f[1], ""))
                if v is None or not (f[2] <= v <= f[3]):
                    ok = False
                    break
        if ok:
            out.append(r)
    return out


def solve(instruction: str, ws: Path):
    """('answer', v, note) | ('infeasible', None, note) | None"""
    path = find_csv(instruction, ws)
    if path is None:
        if not list(ws.rglob("*.csv")) and re.search(r"\.csv\b", instruction):
            return ("infeasible", None, "csv file missing")
        return None
    rows = load_csv(path)
    if not rows:
        return None
    columns = list(rows[0].keys())
    qs = [s for s in re.split(r"(?<=[.?!])\s+", instruction) if s.strip().endswith("?")]
    if len(qs) != 1:
        return None
    q = qs[0].lower().strip()
    # declared columns must exist
    m = re.search(r"has columns ([\w,\s]+?)\s*\(", instruction)
    if m:
        declared = [c.strip() for c in m.group(1).split(",") if c.strip()]
        norm = lambda c: re.sub(r"[\s_]+", "", c).lower()  # noqa: E731
        absent = sorted({norm(c) for c in declared} - {norm(c) for c in columns})
        if absent:
            # The task's own schema promises a column the file does not have:
            # established without any model code, but a signal only -- the task
            # may not need that column, so the LLM still gets a (cheap) look.
            return ("maybe_infeasible", None,
                    f"declared column(s) {', '.join(absent)} absent in {path.name}")
        if set(declared) - set(columns):
            return None  # case/spacing drift only: let the LLM look
    # aggregate
    agg = None
    m = re.match(r"how many units(?: of)?(.*?)(?:were|was)? sold(.*)\?$", q)
    if m and "units" in columns:
        agg = ("sum", "units")
        tail = m.group(1) + " " + m.group(2)
    if agg is None:
        m = re.match(r"what (?:was|is) the total (revenue|sales)(?: \(units ?\* ?price\))?(.*)\?$", q)
        if m and "units" in columns and "price" in columns:
            agg = ("revenue",)
            tail = m.group(2)
    if agg is None:
        m = re.match(r"how many (orders|rows|records|transactions)(.*)\?$", q)
        if m:
            agg = ("count",)
            tail = m.group(2)
    if agg is None:
        return None
    filters, leftover = _parse_filters(" " + tail + " ", columns)
    # everything in the tail must be consumed by filters
    rest = re.sub(r"\b(of|for|in|were|was|sold|placed|the|total|inclusive|with|"
                  r"there|are|is|have|has|been|had|in total|overall|altogether)\b", " ", leftover)
    if re.sub(r"[\s,]+", "", rest):
        return None
    # Empty selection: is "SUM over nothing" = 0 or "insufficient data"?
    # Undecided by the organizers.  Policy via HARNESS_EMPTY_SELECTION:
    #   zero (default) - answer 0 when file and columns exist (a full table
    #                    with no matching rows has a well-defined SUM/COUNT);
    #   infeasible     - treat a value absent from the column as infeasible.
    policy = os.environ.get("HARNESS_EMPTY_SELECTION", "zero")
    empty_note = ""
    for f in filters:
        if f[0] == "eq":
            vals = {str(r.get(f[1], "")).strip().lower() for r in rows}
            if f[2].strip().lower() not in vals:
                if policy == "infeasible":
                    return ("infeasible", None, f"value {f[2]!r} absent in column {f[1]}")
                empty_note = f"; DISPUTED: value {f[2]!r} absent in column {f[1]}"
        if f[0] == "range":
            if f[2] > f[3]:
                return None  # inverted range: let the LLM read the wording
            vals = [v for v in (_num(r.get(f[1], "")) for r in rows) if v is not None]
            if vals and (f[3] < min(vals) or f[2] > max(vals)):
                if policy == "infeasible":
                    return ("infeasible", None, f"range {f[2]}-{f[3]} outside data")
                empty_note = f"; DISPUTED: range {f[2]}-{f[3]} outside data"
    sel = _apply(rows, filters)
    if agg[0] == "sum":
        vals = [_num(r.get(agg[1], "")) for r in sel]
        if any(v is None for v in vals):
            return None
        res = sum(vals)
    elif agg[0] == "revenue":
        vals = [(_num(r["units"]), _num(r["price"])) for r in sel]
        if any(a is None or b is None for a, b in vals):
            return None
        res = sum(a * b for a, b in vals)
    else:
        res = len(sel)
    if isinstance(res, float):
        if not res.is_integer():
            return None
        res = int(res)
    return ("answer", str(res), f"{agg} filters={filters} rows={len(sel)}{empty_note}")


def preview(path: Path, n: int = 4) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    head = "\n".join(lines[: n + 1])
    return f"{path.name}: {len(lines) - 1} data rows\n{head}"
