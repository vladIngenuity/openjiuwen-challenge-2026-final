import concurrent.futures
import unittest
from harness.budget import BudgetLedger


class LedgerTests(unittest.TestCase):
    def test_double_commit_fails(self):
        b = BudgetLedger(total=2000)
        t = b.try_reserve(500)
        self.assertTrue(t)
        b.commit(t, 100, 100)
        with self.assertRaises(ValueError):
            b.commit(t, 100, 100)
        self.assertEqual(b.calls, 1)
        self.assertEqual(b.pending, 0)

    def test_uncertain_disables_new_calls(self):
        b = BudgetLedger(total=3000)
        t = b.try_reserve(500)
        b.commit_uncertain(t, {"error": "timeout"})
        self.assertTrue(b.dead)
        self.assertIsNone(b.try_reserve(100))
        self.assertEqual(b.spent, 500)

    def test_actual_over_reservation_fail_closed(self):
        b = BudgetLedger(total=2000)
        t = b.try_reserve(500)
        b.commit(t, 10000, 500)
        self.assertTrue(b.dead)
        self.assertTrue(b.log[-1]["over_reserved"])

    def test_concurrent_reservation(self):
        b = BudgetLedger(total=2000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            tickets = list(ex.map(b.try_reserve, [250] * 20))
        tickets = [t for t in tickets if t is not None]
        self.assertLessEqual(sum(t.amount for t in tickets), 1700.01)
        for t in tickets:
            b.release(t)
        self.assertAlmostEqual(b.pending, 0)

    def test_cross_ledger_ticket_fails(self):
        a, b = BudgetLedger(total=2000), BudgetLedger(total=2000)
        t = a.try_reserve(200)
        with self.assertRaises(ValueError):
            b.release(t)
        a.release(t)


if __name__ == "__main__":
    unittest.main()
