"""Layer 3 continued: the one-revision loop with mock planners, and whole-lesson verification."""
from __future__ import annotations

import copy

import pytest

from app import contracts
from app.verification import run_with_revision, verify_lesson_plan
from app.verification.loop import PlannerTimeout
from tests.fixtures import SOURCE, context_packet_fixture, lesson_plan_fixture, proposal_fixture, scene_fixture


class ScriptedPlanner:
    """A planner whose first and second answers are fixed in advance."""
    def __init__(self, first, second=None, revise_uses_instruction=False):
        self.first, self.second = first, second
        self.revise_uses_instruction = revise_uses_instruction
        self.instructions = []

    def plan(self, context):
        if isinstance(self.first, Exception):
            raise self.first
        return copy.deepcopy(self.first)

    def revise(self, context, instruction):
        self.instructions.append(instruction)
        if isinstance(self.second, Exception):
            raise self.second
        if self.revise_uses_instruction:
            # A cooperative planner: fix the value the verifier computed for it.
            fixed = copy.deepcopy(self.first)
            for check in instruction["failed_checks"]:
                if check["code"] == "claim_incorrect":
                    idx = int(check["path"].split("/")[2])
                    fixed["claims"][idx]["claimed"] = check["computed"]
            return fixed
        return copy.deepcopy(self.second)


def wrong_first():
    p = proposal_fixture()
    p["claims"][0]["claimed"] = 5
    return p


def test_correct_first_proposal_needs_no_revision():
    out = run_with_revision(ScriptedPlanner(proposal_fixture()), context_packet_fixture(), scene_fixture())
    assert out.status == "accepted" and len(out.attempts) == 1 and len(out.planner_ms) == 1


def test_wrong_then_fixed_is_accepted_on_attempt_two():
    planner = ScriptedPlanner(wrong_first(), revise_uses_instruction=True)
    out = run_with_revision(planner, context_packet_fixture(), scene_fixture())
    assert [a.status for a in out.attempts] == ["revision_requested", "accepted"]
    assert out.final.attempt == 2
    assert planner.instructions[0]["failed_checks"][0]["computed"] == 4


def test_wrong_twice_is_declined_with_fallback_and_never_a_third_try():
    planner = ScriptedPlanner(wrong_first(), wrong_first())
    out = run_with_revision(planner, context_packet_fixture(), scene_fixture())
    assert [a.status for a in out.attempts] == ["revision_requested", "declined"]
    assert out.final.fallback is not None and len(planner.instructions) == 1


def test_planner_ignoring_attempt_field_cannot_earn_a_third_attempt():
    second = wrong_first(); second["attempt"] = 1   # lies about being a first attempt
    out = run_with_revision(ScriptedPlanner(wrong_first(), second), context_packet_fixture(), scene_fixture())
    assert out.final.status == "declined" and out.final.attempt == 2


def test_planner_timeout_is_declined_with_timeout_fallback():
    out = run_with_revision(ScriptedPlanner(PlannerTimeout()), context_packet_fixture(), scene_fixture())
    assert out.status == "declined" and out.final.reason_codes() == ["planner_timeout"]
    assert "retry" in out.final.fallback["text"]


def test_planner_crash_on_revision_is_declined_not_raised():
    out = run_with_revision(ScriptedPlanner(wrong_first(), RuntimeError("boom")), context_packet_fixture(), scene_fixture())
    assert out.status == "declined" and out.final.reason_codes() == ["planner_provider_error"]


def test_slow_planner_degrades_after_deadline():
    ctx = context_packet_fixture(deadline_ms=10)
    out = run_with_revision(ScriptedPlanner(proposal_fixture()), ctx, scene_fixture(), elapsed_before_ms=50)
    assert out.status == "degraded"


def test_on_result_callback_sees_every_attempt():
    seen = []
    run_with_revision(ScriptedPlanner(wrong_first(), wrong_first()), context_packet_fixture(), scene_fixture(), on_result=seen.append)
    assert [r.status for r in seen] == ["revision_requested", "declined"]


# --------------------------------------------------------------------------- lesson plans
REQUEST = {"request_id": "lesson-request-001", "topic": "derivatives", "approved_source_refs": [SOURCE]}


def test_correct_lesson_plan_is_accepted_and_compiled():
    r = verify_lesson_plan(lesson_plan_fixture(), REQUEST)
    assert r.status == "accepted", r.as_dict()
    node = r.compiled_lesson["nodes"][1]
    assert node["practice"][0]["answer"] == 4
    assert "slope 4" in next(op["text"] for op in node["operations"] if op["type"] == "set_narration")


def test_lesson_plan_second_node_may_use_object_created_in_first():
    plan = lesson_plan_fixture()
    plan["nodes"].append({"node_id": "label-it", "title": "Label", "claims": [],
                          "operations": [{"type": "highlight", "object_id": "graph.tangent"}]})
    assert verify_lesson_plan(plan, REQUEST).status == "accepted"


def test_lesson_plan_with_wrong_claim_requests_revision():
    plan = lesson_plan_fixture()
    plan["nodes"][1]["claims"][0]["claimed"] = 3
    r = verify_lesson_plan(plan, REQUEST)
    assert r.status == "revision_requested" and "claim_incorrect" in r.reason_codes()
    assert contracts.validation_errors("revision_instruction", r.revision_instruction) == []


def test_lesson_plan_for_wrong_topic_is_rejected():
    plan = lesson_plan_fixture(); plan["topic"] = "python-loops"
    r = verify_lesson_plan(plan, REQUEST)
    assert r.status == "rejected" and "topic_mismatch" in r.reason_codes()


def test_lesson_plan_practice_cannot_cite_unverified_claim():
    plan = lesson_plan_fixture()
    plan["nodes"][1]["practice"][0]["claim_ref"] = "c9"
    r = verify_lesson_plan(plan, REQUEST)
    assert "unknown_claim_ref" in r.reason_codes()


def test_lesson_plan_duplicate_node_ids_flagged():
    plan = lesson_plan_fixture()
    plan["nodes"][1]["node_id"] = "intro"
    assert "duplicate_node_id" in verify_lesson_plan(plan, REQUEST).reason_codes()


def test_lesson_plan_second_attempt_failure_is_declined():
    plan = lesson_plan_fixture(); plan["attempt"] = 2
    plan["nodes"][1]["claims"][0]["claimed"] = 3
    r = verify_lesson_plan(plan, REQUEST)
    assert r.status == "declined" and r.fallback["kind"] == "offer_wait_retry_return"
