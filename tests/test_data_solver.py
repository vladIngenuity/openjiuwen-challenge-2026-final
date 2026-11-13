"""Edge cases of the deterministic data_analysis solver (issue #4).

Run: python -m unittest discover tests
"""
import csv
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.solvers import data_solver as D  # noqa: E402

HEADER = ["order_id", "region", "product", "month", "units", "price"]
ROWS = [
    [1, "north", "widget", 1, 5, 10],
    [2, "south", "widget", 2, 7, 12],
    [3, "north", "gadget", 2, 3, 50],
    [4, "east", "widget", 3, 4, 10],
    [5, "west", "gizmo", 3, 9, 20],
    [6, "north", "widget", 4, 6, 11],
]


def ins(q, n=None):
    n = len(ROWS) if n is None else n
    return (f"The file sales.csv has columns order_id,region,product,month,units,price ({n} rows). "
            f"{q} Use bash with python3 to compute it. Work only inside the current directory. "
            "When you are done, write ONLY the final answer to the file answer.txt.")


class Base(unittest.TestCase):
    rows = ROWS
    header = HEADER

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.write(self.rows, self.header)
        os.environ.pop("HARNESS_EMPTY_SELECTION", None)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("HARNESS_EMPTY_SELECTION", None)

    def write(self, rows, header):
        with open(self.ws / "sales.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    def solve(self, q):
        return D.solve(ins(q), self.ws)


class Basic(Base):
    def test_units_month_range(self):
        r = self.solve("How many units of product 'widget' were sold in months 1 through 3 inclusive?")
        self.assertEqual(r[:2], ("answer", "16"))

    def test_units_region(self):
        r = self.solve("How many units of product 'widget' were sold in region 'north'?")
        self.assertEqual(r[:2], ("answer", "11"))

    def test_revenue(self):
        r = self.solve("What is the total revenue (units*price) of product 'widget' in months 1 through 2 inclusive?")
        self.assertEqual(r[:2], ("answer", str(5 * 10 + 7 * 12)))

    def test_orders_count(self):
        r = self.solve("How many orders of product 'widget' were placed in months 1 through 4 inclusive?")
        self.assertEqual(r[:2], ("answer", "4"))

    def test_unknown_question_shape_is_not_guessed(self):
        # averages are not in the deterministic grammar -> None (LLM fallback)
        r = self.solve("What is the average number of units per order for product 'widget', rounded down to an integer?")
        self.assertIsNone(r)


class EmptySelection(Base):
    Q_GHOST = "How many units of product 'doohickey' were sold in months 1 through 3 inclusive?"
    Q_RANGE = "How many units of product 'widget' were sold in months 9 through 11 inclusive?"

    def test_absent_value_zero_policy_default(self):
        r = self.solve(self.Q_GHOST)
        self.assertEqual(r[:2], ("answer", "0"))
        self.assertIn("DISPUTED", r[2])

    def test_absent_value_infeasible_policy(self):
        os.environ["HARNESS_EMPTY_SELECTION"] = "infeasible"
        self.assertEqual(self.solve(self.Q_GHOST)[0], "infeasible")

    def test_range_outside_data(self):
        r = self.solve(self.Q_RANGE)
        self.assertEqual(r[:2], ("answer", "0"))
        os.environ["HARNESS_EMPTY_SELECTION"] = "infeasible"
        self.assertEqual(self.solve(self.Q_RANGE)[0], "infeasible")

    def test_existing_product_without_sales_in_range_is_feasible_zero(self):
        # gizmo exists but only in month 3 -> months 1..2 => 0, never 'infeasible'
        os.environ["HARNESS_EMPTY_SELECTION"] = "infeasible"
        r = self.solve("How many units of product 'gizmo' were sold in months 1 through 2 inclusive?")
        self.assertEqual(r[:2], ("answer", "0"))

    def test_inverted_range_goes_to_llm(self):
        r = self.solve("How many units of product 'widget' were sold in months 3 through 1 inclusive?")
        self.assertIsNone(r)


class DirtyData(Base):
    def test_whitespace_and_case_in_values(self):
        rows = [r[:] for r in ROWS]
        rows[0][2] = "  Widget "
        rows[1][2] = "WIDGET"
        self.write(rows, HEADER)
        r = self.solve("How many units of product 'widget' were sold in months 1 through 3 inclusive?")
        self.assertEqual(r[:2], ("answer", "16"))

    def test_blank_numeric_value_is_not_guessed(self):
        rows = [r[:] for r in ROWS]
        rows[0][4] = ""
        self.write(rows, HEADER)
        r = self.solve("How many units of product 'widget' were sold in months 1 through 3 inclusive?")
        self.assertIsNone(r)

    def test_duplicate_rows_are_counted(self):
        rows = [r[:] for r in ROWS] + [ROWS[0][:]]
        self.write(rows, HEADER)
        r = D.solve(ins("How many units of product 'widget' were sold in months 1 through 3 inclusive?",
                        n=len(rows)), self.ws)
        self.assertEqual(r[:2], ("answer", "21"))

    def test_declared_columns_missing_goes_to_llm(self):
        rows = [r[:5] for r in ROWS]
        self.write(rows, HEADER[:5])          # no price column
        r = self.solve("What is the total revenue (units*price) of product 'widget' in months 1 through 2 inclusive?")
        # still goes to the LLM, now with a maybe_infeasible signal (not an answer, not a claim)
        self.assertEqual(r[0], "maybe_infeasible", r)
        self.assertIn("price", r[2])

    def test_missing_file(self):
        (self.ws / "sales.csv").unlink()
        r = self.solve("How many units of product 'widget' were sold in months 1 through 3 inclusive?")
        self.assertEqual(r[0], "infeasible")


class Metamorphic(Base):
    QUESTIONS = [
        "How many units of product 'widget' were sold in months 1 through 3 inclusive?",
        "How many units of product 'widget' were sold in region 'north'?",
        "What is the total revenue (units*price) of product 'widget' in months 1 through 4 inclusive?",
        "How many orders of product 'widget' were placed in months 1 through 4 inclusive?",
    ]

    def test_row_permutation_does_not_change_answers(self):
        base = [self.solve(q)[:2] for q in self.QUESTIONS]
        rnd = random.Random(0)
        for _ in range(5):
            rows = [r[:] for r in ROWS]
            rnd.shuffle(rows)
            self.write(rows, HEADER)
            self.assertEqual([self.solve(q)[:2] for q in self.QUESTIONS], base)

    def test_column_permutation_does_not_change_answers(self):
        base = [self.solve(q)[:2] for q in self.QUESTIONS]
        perm = [2, 0, 5, 1, 4, 3]
        self.write([[r[i] for i in perm] for r in ROWS], [HEADER[i] for i in perm])
        # the instruction still lists the canonical order; the solver reads by name
        self.assertEqual([self.solve(q)[:2] for q in self.QUESTIONS], base)


if __name__ == "__main__":
    unittest.main()
