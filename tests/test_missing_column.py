"""A data task whose own schema ("has columns ..., units, ...") names a column the
CSV does not have is flagged maybe_infeasible by the deterministic phase,
independently of any model code.  A KeyError in a model's program stays an
execution error (review of #24: revenue = units*price, model reads
row['revenue'] -> must not be an infeasibility claim)."""
import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import llm_solvers as L  # noqa: E402
from harness.solvers import data_solver as D  # noqa: E402

INSTR = ("The file sales.csv has columns order_id,region,product,month,units,price (20 rows). "
         "How many units of product 'gizmo' were sold in months 4 through 7 inclusive?")


def det(header, instruction=INSTR, rows=("6,north,gizmo,5,50,3", "16,south,gizmo,7,5,2")):
    d = Path(tempfile.mkdtemp())
    try:
        n = len(header.split(","))
        body = "\n".join(",".join(r.split(",")[:n]) for r in rows)
        (d / "sales.csv").write_text(header + "\n" + body + "\n")
        return D.solve(instruction, d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


class DeclaredColumnMissing(unittest.TestCase):
    def test_declared_column_absent_is_maybe_infeasible(self):
        r = det("order_id,region,product,month,price")
        self.assertEqual(r[0], "maybe_infeasible", r)
        self.assertIn("units", r[2])

    def test_case_or_spacing_drift_is_not_a_signal(self):
        r = det("Order_ID,region,product,month,Units,price")
        self.assertNotEqual(r and r[0], "maybe_infeasible", r)

    def test_complete_schema_still_answers(self):
        r = det("order_id,region,product,month,units,price")
        self.assertEqual(r[:2], ("answer", "55"), r)

    def test_no_declared_schema_no_signal(self):
        instr = "How many units of product 'gizmo' were sold in months 4 through 7 inclusive? Use sales.csv."
        r = det("order_id,region,product,month,price", instruction=instr)
        self.assertNotEqual(r and r[0], "maybe_infeasible", r)


class StubLLM:
    def __init__(self, content):
        self.content = content
        self.messages = None

    async def chat(self, messages, model, max_tokens, tag):
        self.messages = messages
        return {"content": self.content, "cost": 100.0}


class DetHintInPrompt(unittest.TestCase):
    def _run(self, raw, content="INFEASIBLE"):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "sales.csv").write_text("order_id,region,product,month,price\n6,north,gizmo,5,3\n")
            task = SimpleNamespace(ws=d, instruction=INSTR, check="exact_int", cost=0.0,
                                   task_id="data_x", raw=raw)
            llm = StubLLM(content)
            r = asyncio.run(L.solve_data(llm, task))
            return r, llm.messages[-1]["content"]
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_maybe_infeasible_note_reaches_the_model(self):
        sig = det("order_id,region,product,month,price")
        r, prompt = self._run({"_det": sig})
        self.assertIn("declared column(s) units absent in sales.csv", prompt)
        self.assertIn("print INFEASIBLE", prompt)
        self.assertEqual(r[0], "infeasible", r)   # the model's own claim

    def test_no_note_without_signal(self):
        for raw in ({}, {"_det": None}, {"_det": ("answer", "5", "x")}):
            _, prompt = self._run(raw)
            self.assertNotIn("automatic check", prompt)


class KeyErrorIsExecutionError(unittest.TestCase):
    def setUp(self):
        code, out = L.sandbox.run_python("print(1)", Path(tempfile.gettempdir()))
        if code != 0:
            self.skipTest(f"sandbox unavailable here: {out[:80]}")

    def _solve(self, header, column, instruction):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "sales.csv").write_text(header + "\n2,5\n")
            task = SimpleNamespace(ws=d, instruction=instruction, check="exact_int", cost=0.0,
                                   task_id="data_x")
            prog = ("```python\nimport csv\nprint(sum(int(r[%r]) for r in "
                    "csv.DictReader(open('sales.csv'))))\n```" % column)
            return asyncio.run(L.solve_data(StubLLM(prog), task))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_reviewer_counterexample(self):
        r = self._solve("units,price", "revenue",
                        "The file sales.csv has columns units,price. "
                        "What is the total revenue (revenue = units * price)?")
        self.assertEqual(r[0], "error", r)

    def test_declared_but_absent_column_keyerror_is_still_an_error(self):
        r = self._solve("units,price", "qty", "The file sales.csv has columns units,qty,price. "
                                              "What is the total qty?")
        self.assertEqual(r[0], "error", r)


if __name__ == "__main__":
    unittest.main()
