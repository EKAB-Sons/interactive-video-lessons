import unittest
from app.engine import run_interruption

class InterruptionFlowTests(unittest.TestCase):
    def test_successful_branch_returns_to_anchor_and_links_events(self):
        result=run_interruption()
        self.assertEqual(result["status"], "resumed")
        self.assertEqual(result["session"].lesson["node_id"], "distance-time-tangent")
        self.assertEqual(result["session"].branches[0]["return_anchor"]["node_id"], "distance-time-tangent")
        self.assertEqual({e["request_id"] for e in result["events"]}, {"request-demo-001"})

    def test_invalid_cases_do_not_create_branch_or_compile(self):
        for scenario in ("malformed", "unsupported", "stale", "timeout", "ambiguous"):
            self.assertFalse(run_interruption(scenario=scenario)["session"].branches)
        self.assertEqual(run_interruption(selected_object_id="not-real")["status"], "needs_clarification")
