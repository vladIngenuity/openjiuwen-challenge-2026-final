import unittest

from tools.analyze_model_routing import replay_episode


def row(category, reward, correct):
    return {
        "category": category,
        "reward": reward,
        "verdict": "correct_text" if correct else "wrong_text",
    }


class RoutingReplayTests(unittest.TestCase):
    def test_hybrid_selects_reason_only_for_math_and_coding(self):
        ids = ["m", "s", "d", "c"]
        rows = {
            "fast": {
                "m": row("math", 4, False),
                "s": row("search", 3, True),
                "d": row("data_analysis", 2, True),
                "c": row("coding", 5, False),
            },
            "reason": {
                "m": row("math", 4, True),
                "s": row("search", 3, False),
                "d": row("data_analysis", 2, False),
                "c": row("coding", 5, True),
            },
        }
        costs = {
            "fast": {task_id: 10 for task_id in ids},
            "reason": {task_id: 20 for task_id in ids},
        }

        reward, spent, completed = replay_episode(
            ids, rows, costs, "math_coding_reason", 100
        )

        self.assertEqual(reward, 14)
        self.assertEqual(spent, 60)
        self.assertEqual(completed, 4)

    def test_replay_never_exceeds_budget(self):
        ids = ["a", "b"]
        rows = {
            action: {
                task_id: row("math", 5, True) for task_id in ids
            }
            for action in ("fast", "reason")
        }
        costs = {
            "fast": {task_id: 10 for task_id in ids},
            "reason": {task_id: 70 for task_id in ids},
        }

        reward, spent, completed = replay_episode(
            ids, rows, costs, "all_reason", 100
        )

        self.assertEqual(reward, 5)
        self.assertEqual(spent, 70)
        self.assertEqual(completed, 1)


if __name__ == "__main__":
    unittest.main()
