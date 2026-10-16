"""End-to-end demo flow on the verifier. Kept as unittest for CI compatibility."""
import unittest

from app.engine import run_interruption
from app.telemetry import telemetry


class InterruptionFlowTests(unittest.TestCase):
    def setUp(self):
        telemetry.clear()

    def test_successful_branch_returns_to_anchor_and_links_events(self):
        result = run_interruption()
        self.assertEqual(result["status"], "resumed")
        self.assertEqual(result["session"].lesson["node_id"], "distance-time-tangent")
        self.assertEqual(result["session"].branches[0]["return_anchor"]["node_id"], "distance-time-tangent")
        self.assertEqual({e["request_id"] for e in result["events"]}, {"request-demo-001"})
        narration = next(op for op in result["scene_update"]["operations"] if op["type"] == "set_narration")
        self.assertIn("approaches 4", narration["text"])

    def test_invalid_cases_do_not_create_branch_or_compile(self):
        for scenario in ("malformed", "unsupported", "wrong_maths"):
            # repairable: one revision, then accepted
            r = run_interruption(scenario=scenario)
            self.assertEqual(r["status"], "resumed", scenario)
            self.assertEqual([e["status"] for e in r["events"] if e["stage"] == "verification"], ["revision_requested", "accepted"], scenario)
        for scenario in ("wrong_twice", "timeout"):
            r = run_interruption(scenario=scenario)
            self.assertEqual(r["status"], "fallback", scenario)
            self.assertFalse(r["session"].branches)
        self.assertEqual(run_interruption(scenario="stale")["status"], "rejected")
        self.assertEqual(run_interruption(scenario="ambiguous")["status"], "needs_clarification")
        self.assertEqual(run_interruption(selected_object_id="not-real")["status"], "needs_clarification")

    def test_wrong_twice_fallback_only_states_verified_values(self):
        r = run_interruption(scenario="wrong_twice")
        self.assertEqual(r["fallback"]["kind"], "checked_text")
        self.assertIn("approach 4", r["fallback"]["text"])   # c2 verified: secant slopes approach 4
        self.assertNotIn(" 5", r["fallback"]["text"])

    def test_m7_telemetry_emitted_per_attempt(self):
        run_interruption(scenario="wrong_maths")
        m7 = telemetry.events("M7", "request-demo-001")
        self.assertEqual([e["status"] for e in m7], ["revision_requested", "accepted"])
        self.assertTrue(all(e["verifier_version"] and e["planner_id"] == "mock-planner" for e in m7))
        self.assertTrue(any(e["status"] == "mismatch" for e in telemetry.events("M6")))


if __name__ == "__main__":
    unittest.main()
