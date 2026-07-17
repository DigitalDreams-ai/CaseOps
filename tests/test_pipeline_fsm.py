import unittest

from pipeline_fsm import ALLOWED, record_transition, validate_transition


class PipelineFsmTests(unittest.TestCase):
    def test_every_allowed_edge_accepts(self):
        for source, targets in ALLOWED.items():
            for target in targets:
                with self.subTest(source=source, target=target):
                    self.assertTrue(validate_transition({}, source, target).ok)

    def test_illegal_edges_reject(self):
        for source, target in ((4, 6), (5, 8), (7, 9), (10, 5), (2, 5)):
            with self.subTest(source=source, target=target):
                result = validate_transition({}, source, target)
                self.assertFalse(result.ok)
                self.assertEqual(result.violation, "illegal_transition")

    def test_engineering_and_support_paths(self):
        self.assertTrue(validate_transition({}, 7, 10).ok)
        self.assertTrue(validate_transition({}, 7, 8).ok)
        self.assertEqual(validate_transition({}, 8, 10).violation, "illegal_transition")

    def test_fourth_loop_exceeds_cap(self):
        state = {"loop_counts": {"6->5": 0}}
        for count in range(3):
            state["loop_counts"]["6->5"] = count
            self.assertTrue(validate_transition(state, 6, 5).ok)
        state["loop_counts"]["6->5"] = 3
        self.assertEqual(validate_transition(state, 6, 5).violation, "loop_cap_exceeded")

    def test_same_step_repeat_is_legal_without_loop_increment(self):
        state = record_transition({}, 6, "2026-07-16T00:00:00Z")
        state = record_transition(state, 6, "2026-07-16T00:01:00Z")
        self.assertIsNone(state["transitions"][-1]["violation"])
        self.assertEqual(state["loop_counts"], {})

    def test_corrupt_loop_counter_is_treated_as_zero(self):
        state = {"loop_counts": {"6->5": "not-a-number"}}
        self.assertTrue(validate_transition(state, 6, 5).ok)
        state = record_transition({"transitions": [{"step": 6, "at": "earlier", "violation": None}], **state}, 5, "now")
        self.assertEqual(state["loop_counts"]["6->5"], 1)


if __name__ == "__main__":
    unittest.main()
