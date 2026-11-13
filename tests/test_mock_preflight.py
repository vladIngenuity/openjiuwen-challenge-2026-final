"""Mock proxy must return valid responses to both regular and preflight calls.

Regression for undefined 'text' in mock_llm.H.answer which caused every
proxied request to disconnect and made CI report zero confirmed token usage.
"""
import json
import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mock_llm import H


class MockPreflightTest(unittest.TestCase):
    def setUp(self):
        self.h = H.__new__(H)
        self.h.server = SimpleNamespace(cfg=SimpleNamespace(
            rnd=random.Random(31), noise=0.0))

    def test_regular_request_answer_path(self):
        response, calls = self.h.answer(
            {"model": "qwen3.8-27b-noreason"},
            [{"role": "user", "content": "Ordinary query"}],
            None, {})
        self.assertEqual(response, "INFEASIBLE")
        self.assertEqual(calls, [])

    def test_preflight_returns_valid_ratings_without_truth(self):
        rows = [{"id": 0, "kind": "math", "reward": 2,
                 "prompt": "some task", "files": 0, "bytes": 0, "det": "none"},
                {"id": 1, "kind": "coding", "reward": 3,
                 "prompt": "fix a test", "files": 2, "bytes": 1000, "det": "none"}]
        prompt = ("Estimate probabilities. Do not mark tasks infeasible. "
                  "Return exactly a JSON array of 2 integers." + chr(10)
                  + json.dumps(rows))
        resp, calls = self.h.answer(
            {"model": "qwen3.8-27b-noreason"},
            [{"role": "user", "content": prompt}], None, {})
        ratings = json.loads(resp)
        self.assertEqual(len(ratings), 2)
        self.assertTrue(all(type(x) is int and 0 <= x <= 10 for x in ratings))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
