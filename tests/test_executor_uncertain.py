"""Regression: reporting an HTTP 503 must not throw TypeError at int(None).
No API calls. Uses the existing harness modules under test.
"""
import unittest
from types import SimpleNamespace
from harness.executor import StrategyExecutor

class UncertainCallTests(unittest.TestCase):
    def test_calls_since_handles_null_usage(self):
        obj = object.__new__(StrategyExecutor)
        obj.h = SimpleNamespace(ledger=SimpleNamespace(log=[
            {'tag':'math:math_0071', 'model':'qwen3.8-27b', 'transport':'raw',
             'in':None, 'out':None, 'reason':None, 'cost':639.5,
             'sec':2.0, 'error':'transient', 'accounting':'uncertain_full_reservation'},
            {'tag':'math:math_0055', 'model':'qwen3.8-27b', 'transport':'raw',
             'in':152, 'out':242, 'reason':68, 'cost':257.2}
        ]))
        calls = obj._calls_since(0, 'math_0071')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].cost, 639.5)
        self.assertEqual(calls[0].error, 'transient')
        self.assertEqual(calls[0].input_tokens, 0)  # display-only; ledger remains unknown
        self.assertEqual(obj.h.ledger.log[0]['in'], None)

if __name__ == '__main__':
    unittest.main()
