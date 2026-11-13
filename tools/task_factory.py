#!/usr/bin/env python3
"""Task Factory: generates training tasks in the organizers' format.

    python tools/task_factory.py OUT_DIR --n 100 --seed 1 [--infeasible 0.2]

Each task gets task.json (+workspace).  Ground truth is written to a separate
file OUT_DIR/../<name>_truth.json (never inside the task dir) so the harness
cannot see it.  Coding tasks also get hidden tests in the truth file.
Includes phrasings that the deterministic solvers do NOT know, to measure
fallback behaviour, and controlled infeasible variants.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import textwrap
from pathlib import Path

TAIL_NUM = (" Work only inside the current directory. When you are done, write ONLY the final "
            "answer to the file answer.txt in the current directory (for example with bash: "
            "echo 42 > answer.txt).")
TAIL_CODE = (" Work only inside the current directory. When you are done, write ONLY the word "
             "DONE to the file answer.txt in the current directory (for example with bash: "
             "echo 42 > answer.txt).")

FIRST = ["Alice", "Boris", "Chen", "Dmitri", "Farid", "Grace", "Hiro", "Irina", "Jonas", "Kira",
         "Maya", "Nikolai", "Olga", "Pavel", "Quinn", "Rosa", "Sergei", "Tanya", "Uma", "Viktor"]
LAST = ["Garcia", "Haddad", "Ivanova", "Kowalski", "Muller", "Novak", "Petrov", "Sato", "Smith",
        "Wang", "Lopez", "Okafor"]
COMPANIES = ["Arktika Labs", "Bluefin Systems", "Cobalt Works", "Dune Robotics", "Ember Bio",
             "Fjord Data", "Granite AI", "Helix Motors", "Iris Optics", "Juniper Foods",
             "Kestrel Energy", "Lumen Health"]
CITIES = ["Osaka", "Medan", "Lyon", "Porto", "Kazan", "Austin", "Leeds", "Turin", "Busan",
          "Accra", "Quito", "Perth"]


# ------------------------------------------------------------------- math
def gen_math(rnd: random.Random, infeasible: bool):
    x = rnd.randint(500, 3000)
    start = x
    known = rnd.random() < 0.8   # 20% use phrasings outside the deterministic grammar
    sents = [f"A warehouse starts with {x} boxes."]
    expr_ops = []
    for _ in range(rnd.randint(2, 5)):
        k = rnd.choice(["ship", "recv", "split", "double", "sell", "pct"] if known else
                       ["give_frac", "lose_each", "triple_minus", "ship", "split"])
        if k == "ship":
            a, d = rnd.randint(5, 60), rnd.randint(2, 6)
            sents.append(f"It ships {a} boxes per day for {d} days.")
            x -= a * d
        elif k == "recv":
            n, a = rnd.randint(2, 4), rnd.randint(20, 120)
            sents.append(f"It receives {n} deliveries of {a} boxes each.")
            x += n * a
        elif k == "split":
            m = rnd.randint(2, 4)
            sents.append(f"Then the stock is split equally into {m} warehouses and it keeps "
                         f"one share (rounded down).")
            x //= m
        elif k == "double":
            sents.append("Then the stock is doubled by merging with a sister warehouse.")
            x *= 2
        elif k == "sell":
            a = rnd.randint(10, 90)
            sents.append(f"Then it sells {a} boxes.")
            x -= a
        elif k == "pct":
            p = rnd.choice([10, 20, 25, 50])
            sents.append(f"Then the stock decreases by {p}% (rounded down).")
            x = x * (100 - p) // 100
        elif k == "give_frac":
            sents.append("Then it gives away a quarter of its boxes (rounded down) to a charity.")
            x -= x // 4
        elif k == "lose_each":
            n, a = rnd.randint(2, 5), rnd.randint(3, 15)
            sents.append(f"During {n} storms it loses {a} boxes in each storm.")
            x -= n * a
        elif k == "triple_minus":
            a = rnd.randint(10, 50)
            sents.append(f"Next the number of boxes is tripled and then {a} damaged ones are "
                         f"thrown out.")
            x = x * 3 - a
        expr_ops.append(k)
    if infeasible:
        # remove the starting amount or add an unknown quantity
        if rnd.random() < 0.5:
            sents[0] = "A warehouse starts with some boxes."
        else:
            sents.insert(2, "Then it receives an unknown number of extra boxes from a supplier.")
    q = "How many boxes does it have at the end?"
    ins = " ".join(sents) + " " + q + " Compute it with the bash tool (python3 -c)." + TAIL_NUM
    return {"task_type": "math", "instruction": ins, "check": "exact_int"}, \
        {"expected": None if infeasible else str(x), "start": start}


# ----------------------------------------------------------------- search
def gen_kb(rnd: random.Random, n_people=30):
    people = []
    used = set()
    while len(people) < n_people:
        n = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        if n not in used:
            used.add(n)
            people.append(n)
    comps = rnd.sample(COMPANIES, 10)
    cities = rnd.sample(CITIES, 10)
    kb = {}
    for c, city in zip(comps, cities):
        kb[c] = {"Headquarters": city, "Founded": str(rnd.randint(1950, 2020))}
    for p in people:
        kb[p] = {"Born": str(rnd.randint(1960, 2001)), "Employer": rnd.choice(comps),
                 "Mentor": rnd.choice([q for q in people if q != p])}
    return kb, people, comps


def write_kb(ws: Path, kb: dict, comps):
    d = ws / "kb"
    d.mkdir(parents=True)
    for name, attrs in kb.items():
        kind = "company" if name in comps else "person"
        fn = d / f"{kind}_{name.lower().replace(' ', '_')}.md"
        body = f"# {name}\n\n" + "\n".join(f"{k}: {v}" for k, v in attrs.items()) + "\n"
        fn.write_text(body)


def gen_search(rnd: random.Random, infeasible: bool):
    kb, people, comps = gen_kb(rnd)
    p = rnd.choice(people)
    kind = rnd.choice(["born", "hq", "founded", "mentor", "mentor_born", "mentor_employer",
                       "employer", "mentor_hq", "phr_born", "phr_hq"])
    a = kb[p]
    if kind == "born":
        q, ans = f"In which year was {p} born?", a["Born"]
    elif kind == "phr_born":
        q, ans = f"What is the birth year of {p}?", a["Born"]
    elif kind == "hq":
        q, ans = f"In which city is the headquarters of {p}'s employer?", kb[a["Employer"]]["Headquarters"]
    elif kind == "phr_hq":
        q, ans = f"Where is the company that {p} works for headquartered?", kb[a["Employer"]]["Headquarters"]
    elif kind == "founded":
        q, ans = f"In which year was {p}'s employer founded?", kb[a["Employer"]]["Founded"]
    elif kind == "mentor":
        q, ans = f"Who is the mentor of {p}?", a["Mentor"]
    elif kind == "mentor_born":
        q, ans = f"In which year was {p}'s mentor born?", kb[a["Mentor"]]["Born"]
    elif kind == "mentor_employer":
        q, ans = f"Which company employs {p}'s mentor?", kb[a["Mentor"]]["Employer"]
    elif kind == "employer":
        q, ans = f"Who is {p}'s employer?", a["Employer"]
    else:
        q, ans = (f"In which city is the headquarters of the employer of {p}'s mentor?",
                  kb[kb[a["Mentor"]]["Employer"]]["Headquarters"])
    if infeasible:
        mode = rnd.choice(["ghost", "drop_company", "drop_attr"])
        if mode == "drop_company" and kind not in ("hq", "phr_hq", "founded", "mentor_hq"):
            mode = "drop_attr"
        if mode == "drop_attr" and kind == "mentor_employer":
            kb[a["Mentor"]].pop("Employer", None)
            mode = "done"
        if mode == "ghost" or kind in ("born", "phr_born", "mentor", "employer"):
            ghost = f"{rnd.choice(FIRST)} {rnd.choice(['Zubov', 'Lindqvist', 'Moreau'])}"
            q = q.replace(p, ghost)
        elif mode == "drop_company":
            emp = kb[a["Employer"]] if "mentor" not in kind else kb[kb[a["Mentor"]]["Employer"]]
            emp.pop("Headquarters", None)
            emp.pop("Founded", None)
        elif mode == "drop_attr":
            if "mentor" in kind:
                kb[p].pop("Mentor", None)
            else:
                kb[p].pop("Employer", None)
        ans = None
    ins = ("The directory kb/ contains a small knowledge base of markdown files. " + q +
           " Use the file tools or bash (ls, grep, cat) to find it." + TAIL_NUM)
    return {"task_type": "search", "instruction": ins, "check": "exact_str"}, \
        {"expected": ans, "_kb": kb, "_comps": comps}


# ------------------------------------------------------------------- data
def gen_data(rnd: random.Random, infeasible: bool):
    n = rnd.choice([20, 50, 120, 300])
    rows = []
    for i in range(1, n + 1):
        rows.append({"order_id": i, "region": rnd.choice(["north", "south", "east", "west"]),
                     "product": rnd.choice(["widget", "gadget", "gizmo", "sprocket"]),
                     "month": rnd.randint(1, 12), "units": rnd.randint(1, 40),
                     "price": rnd.randint(5, 99)})
    prod = rnd.choice(["widget", "gadget", "gizmo", "sprocket"])
    m1 = rnd.randint(1, 11)
    m2 = rnd.randint(m1, min(12, m1 + 3))
    kind = rnd.choice(["units_range", "units_region", "revenue", "orders", "avg_units",
                       "max_price", "units_zero"])
    if kind == "units_zero":
        # independent check: product exists, but has no sales in these months,
        # so the correct (feasible) answer is 0
        rows = [r for r in rows if not (r["product"] == prod and m1 <= r["month"] <= m2)]
        for i, r in enumerate(rows, 1):
            r["order_id"] = i
        n = len(rows)
        kind = "units_range"
    sel = [r for r in rows if r["product"] == prod and m1 <= r["month"] <= m2]
    if kind == "units_range":
        q = f"How many units of product '{prod}' were sold in months {m1} through {m2} inclusive?"
        ans = sum(r["units"] for r in sel)
    elif kind == "units_region":
        reg = rnd.choice(["north", "south", "east", "west"])
        q = f"How many units of product '{prod}' were sold in region '{reg}'?"
        ans = sum(r["units"] for r in rows if r["product"] == prod and r["region"] == reg)
    elif kind == "revenue":
        q = (f"What is the total revenue (units*price) of product '{prod}' in months {m1} "
             f"through {m2} inclusive?")
        ans = sum(r["units"] * r["price"] for r in sel)
    elif kind == "orders":
        q = f"How many orders of product '{prod}' were placed in months {m1} through {m2} inclusive?"
        ans = len(sel)
    elif kind == "avg_units":
        q = (f"What is the average number of units per order for product '{prod}', rounded "
             f"down to an integer?")
        s = [r["units"] for r in rows if r["product"] == prod]
        ans = sum(s) // len(s)
    else:
        q = f"What is the highest price among orders in region 'north' for product '{prod}'?"
        s = [r["price"] for r in rows if r["product"] == prod and r["region"] == "north"]
        ans = max(s) if s else 0
    if infeasible:
        mode = rnd.choice(["ghost_product", "missing_column"])
        if mode == "ghost_product":
            q = q.replace(f"'{prod}'", "'doohickey'")
        else:
            for r in rows:
                r.pop("units" if "units" in q or kind == "orders" else "price", None)
        ans = None
    cols = list(rows[0].keys())
    ins = (f"The file sales.csv has columns order_id,region,product,month,units,price ({n} rows). "
           f"{q} Use bash with python3 to compute it." + TAIL_NUM)
    return {"task_type": "data_analysis", "instruction": ins, "check": "exact_int"}, \
        {"expected": None if ans is None else str(ans), "_rows": rows, "_cols": cols}


# ----------------------------------------------------------------- coding
LIB = {
    "maximum": ("def maximum(xs):\n    best = xs[0]\n    for x in xs:\n        if x > best:\n"
                "            best = x\n    return best\n",
                [("[3, 9, 2]", "9"), ("[-5, -2, -9]", "-2"), ("[7]", "7"), ("[1, 1, 4, 4]", "4")]),
    "minimum": ("def minimum(xs):\n    best = xs[0]\n    for x in xs:\n        if x < best:\n"
                "            best = x\n    return best\n",
                [("[3, 9, 2]", "2"), ("[-5, -2, -9]", "-9"), ("[7]", "7")]),
    "total": ("def total(xs):\n    s = 0\n    for x in xs:\n        s += x\n    return s\n",
              [("[1, 2, 3]", "6"), ("[]", "0"), ("[-4, 10]", "6")]),
    "average": ("def average(xs):\n    return sum(xs) / len(xs)\n",
                [("[2, 4, 6]", "4"), ("[1, 2]", "1.5"), ("[5]", "5")]),
    "reverse_words": ("def reverse_words(s):\n    return ' '.join(reversed(s.split()))\n",
                      [("'c a b'", "'b a c'"), ("'hello world'", "'world hello'"), ("'x'", "'x'")]),
    "count_even": ("def count_even(xs):\n    return sum(1 for x in xs if x % 2 == 0)\n",
                   [("[1, 2, 4, 6, 7]", "3"), ("[]", "0"), ("[0, -2, 3]", "2"), ("[1, 3]", "0")]),
    "first_n": ("def first_n(xs, n):\n    return xs[:n]\n",
                [("[5, 6, 7, 8], 3", "[5, 6, 7]"), ("[1, 2], 0", "[]"), ("[1, 2], 5", "[1, 2]")]),
    "is_palindrome": ("def is_palindrome(s):\n    s = s.lower()\n    return s == s[::-1]\n",
                      [("'Level'", "True"), ("'abc'", "False"), ("''", "True"), ("'abba'", "True")]),
    "count_vowels": ("def count_vowels(s):\n    n = 0\n    for c in s.lower():\n        if c in 'aeiou':\n"
                     "            n += 1\n    return n\n",
                     [("'Hello'", "2"), ("'xyz'", "0"), ("'AEIOU'", "5")]),
    "factorial": ("def factorial(n):\n    r = 1\n    for i in range(2, n + 1):\n        r *= i\n    return r\n",
                  [("5", "120"), ("0", "1"), ("1", "1"), ("6", "720")]),
    "clamp": ("def clamp(x, lo, hi):\n    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n"
              "    return x\n",
              [("5, 0, 10", "5"), ("-3, 0, 10", "0"), ("42, 0, 10", "10")]),
    "running_sum": ("def running_sum(xs):\n    out = []\n    s = 0\n    for x in xs:\n        s += x\n"
                    "        out.append(s)\n    return out\n",
                    [("[1, 2, 3]", "[1, 3, 6]"), ("[]", "[]"), ("[5, -5]", "[5, 0]")]),
    "last_n": ("def last_n(xs, n):\n    if n == 0:\n        return []\n    return xs[-n:]\n",
               [("[1, 2, 3, 4], 2", "[3, 4]"), ("[1, 2], 0", "[]"), ("[9], 1", "[9]")]),
    "capitalize_words": ("def capitalize_words(s):\n    return ' '.join(w.capitalize() for w in s.split())\n",
                         [("'hello big world'", "'Hello Big World'"), ("'a'", "'A'")]),
}


def mutate_src(src: str, rnd: random.Random):
    import ast
    import copy
    tree = ast.parse(src)
    swaps = []
    for i, n in enumerate(ast.walk(tree)):
        if isinstance(n, ast.Compare):
            swaps.append((i, "cmp"))
        elif isinstance(n, (ast.BinOp, ast.AugAssign)):
            swaps.append((i, "op"))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in (
                "reversed", "sum", "max", "min", "len"):
            swaps.append((i, "call"))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in (
                "lower", "capitalize", "append"):
            swaps.append((i, "meth"))
        elif isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
            swaps.append((i, "const"))
        elif isinstance(n, ast.Slice):
            swaps.append((i, "slice"))
    rnd.shuffle(swaps)
    for idx, kind in swaps:
        t2 = copy.deepcopy(tree)
        node = list(ast.walk(t2))[idx]
        if kind == "cmp":
            m = {ast.Gt: ast.Lt, ast.Lt: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
                 ast.GtE: ast.Gt, ast.LtE: ast.Lt, ast.In: ast.NotIn}
            if type(node.ops[0]) not in m:
                continue
            node.ops[0] = m[type(node.ops[0])]()
        elif kind == "op":
            m = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add, ast.Div: ast.FloorDiv,
                 ast.Mod: ast.FloorDiv}
            if type(node.op) not in m:
                continue
            node.op = m[type(node.op)]()
        elif kind == "call":
            m = {"reversed": "sorted", "sum": "len", "max": "min", "min": "max", "len": "sum"}
            node.func.id = m[node.func.id]
        elif kind == "meth":
            m = {"lower": "upper", "capitalize": "upper", "append": "extend"}
            node.func.attr = m[node.func.attr]
        elif kind == "const":
            node.value = node.value + rnd.choice([1, -1])
        elif kind == "slice":
            if node.upper is not None:
                node.upper = ast.BinOp(left=node.upper, op=ast.Add(), right=ast.Constant(1))
            elif node.step is not None:
                node.step = None
            else:
                continue
        ast.fix_missing_locations(t2)
        return ast.unparse(t2) + "\n"
    return None


def gen_coding(rnd: random.Random, infeasible: bool):
    names = rnd.sample(sorted(LIB), rnd.randint(4, 6))
    n_bugs = rnd.randint(1, min(3, len(names)))
    buggy = set(rnd.sample(names, n_bugs))
    srcs = []
    for nm in names:
        src, cases = LIB[nm]
        if nm in buggy:
            for _ in range(20):
                m = mutate_src(src, rnd)
                if m is None:
                    continue
                # mutant must fail the first visible case
                ns1, ns2 = {}, {}
                exec(src, ns1)
                exec(m, ns2)
                a = cases[0][0]
                try:
                    good = eval(f"f({a})", {"f": ns1[nm]})
                    try:
                        bad = eval(f"f({a})", {"f": ns2[nm]})
                    except Exception:  # noqa: BLE001
                        bad = object()
                    if bad != good:
                        src = m
                        break
                except Exception:  # noqa: BLE001
                    continue
        srcs.append(src)
    lib = "\n\n".join(srcs)
    tests = ["import unittest", "", "import mylib as m", "", "", "class T(unittest.TestCase):"]
    hidden = list(tests)
    for nm in names:
        cases = LIB[nm][1]
        a, e = cases[0]
        tests.append(f"    def test_{nm}(self):\n        self.assertEqual(m.{nm}({a}), {e})\n")
        body = "\n".join(f"        self.assertEqual(m.{nm}({a}), {e})" for a, e in cases)
        hidden.append(f"    def test_{nm}(self):\n{body}\n")
    if infeasible:
        nm = names[0]
        a, e = LIB[nm][1][0]
        tests.append(f"    def test_{nm}_again(self):\n        self.assertNotEqual(m.{nm}({a}), {e})\n")
    tail = ["", "if __name__ == '__main__':", "    unittest.main()", ""]
    ins = ("Run `python3 test_mylib.py` in the current directory; some tests fail. Fix the bugs in "
           "mylib.py (do not edit the tests) until all tests pass." + TAIL_CODE)
    return {"task_type": "coding", "instruction": ins, "check": "unittest"}, \
        {"expected": None if infeasible else "tests_pass", "_lib": lib,
         "_tests": "\n".join(tests + tail), "_hidden": "\n".join(hidden + tail)}


GENS = {"math": gen_math, "search": gen_search, "data_analysis": gen_data, "coding": gen_coding}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--infeasible", type=float, default=0.2)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    truth = {}
    types = list(GENS)
    for i in range(a.n):
        ty = types[i % 4]
        inf = rnd.random() < a.infeasible
        spec, tr = GENS[ty](rnd, inf)
        tid = f"{ty}_{i:04d}"
        d = out / tid
        ws = d / "workspace"
        ws.mkdir(parents=True)
        if ty == "search":
            write_kb(ws, tr.pop("_kb"), tr.pop("_comps"))
        elif ty == "data_analysis":
            rows, cols = tr.pop("_rows"), tr.pop("_cols")
            with open(ws / "sales.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)
        elif ty == "coding":
            (ws / "mylib.py").write_text(tr.pop("_lib"))
            (ws / "test_mylib.py").write_text(tr.pop("_tests"))
        spec = {"task_id": tid, **spec, "reward": rnd.randint(1, 10)}
        (d / "task.json").write_text(json.dumps(spec, indent=2))
        truth[tid] = {"type": ty, "reward": spec["reward"], "feasible": not inf, **tr}
    (out.parent / f"{out.name}_truth.json").write_text(json.dumps(truth, indent=1))
    print(f"generated {a.n} tasks in {out}")


if __name__ == "__main__":
    main()
