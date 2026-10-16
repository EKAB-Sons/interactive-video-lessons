"""Local demo of a checked lesson interruption.

Runs mock planner scenarios through the Verification and Policy Layer and
emits the same JSONL trace shape the orchestrator will use in production.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any

from .telemetry import Telemetry, telemetry as default_telemetry
from .verification import run_with_revision
from .verification.loop import PlannerTimeout

SOURCE = "fixture:derivatives-tangent-v1"


def lesson_fixture() -> dict[str, Any]:
    return {
        "lesson_id": "derivatives-intro-v1",
        "objective": "Relate tangent slope to instantaneous speed.",
        "node_id": "distance-time-tangent",
        "scene_version": 7,
        "topic": "derivatives",
        "nodes": ["intro", "distance-time-tangent", "secant-limit", "summary"],
        "objects": {
            "graph.axes": {"kind": "axis", "origin": "base"},
            "graph.curve": {"kind": "curve", "expression": "t**2", "var": "t", "domain": [0, 4], "origin": "base"},
            "graph.tangent": {"kind": "line", "curve": "graph.curve", "at_x": 2, "origin": "base"},
            "graph.secant": {"kind": "line", "origin": "base"},
        },
        "source_refs": [SOURCE],
    }


@dataclass
class Session:
    session_id: str = "session-demo-001"
    lesson: dict[str, Any] = field(default_factory=lesson_fixture)
    branches: list[dict[str, Any]] = field(default_factory=list)


class MockPlanner:
    """Deterministic stand-in for the Lesson Adaptation Builder. Each scenario
    exercises one path through the verifier; the planner itself is never trusted."""
    identifier = "mock-planner"
    config_version = "mock-v2"

    def __init__(self, scenario: str = "success") -> None:
        self.scenario = scenario

    def _proposal(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "adaptation_proposal", "request_id": context["request_id"], "attempt": 1,
            "planner_id": self.identifier, "config_version": self.config_version, "scene_version": context["scene_version"],
            "interpretation": {"question_summary": "Why the tangent slope is the instantaneous speed.",
                               "referents": list(context["selected_object_ids"])},
            "source_refs": [SOURCE],
            "claims": [
                {"id": "c1", "type": "slope_tangent", "expression": "t**2", "var": "t", "at_x": 2, "claimed": 4},
                {"id": "c2", "type": "secant_converges", "expression": "t**2", "var": "t", "at_x": 2, "h_values": [1, 0.5, 0.1, 0.01]},
            ],
            "operations": [
                {"type": "highlight", "object_id": context["selected_object_ids"][0]},
                {"type": "show_secant_sequence", "curve": "graph.curve", "at_x": 2, "h_values": [1, 0.5, 0.1, 0.01], "claim_ref": "c2"},
                {"type": "set_narration", "text": "A secant approaches the tangent; its slope approaches {{claim:c1}}, the instantaneous speed."},
            ],
            "return_anchor": {"node_id": context["node_id"], "scene_version": context["scene_version"]},
        }

    def plan(self, context: dict[str, Any]) -> dict[str, Any]:
        s = self.scenario
        if s == "timeout":
            raise PlannerTimeout()
        if s == "ambiguous":
            return {"kind": "clarification", "request_id": context["request_id"], "status": "needs_clarification",
                    "question": "Do you mean the tangent line or the distance-time curve?",
                    "candidate_object_ids": ["graph.tangent", "graph.curve"]}
        if s == "malformed":
            return {"kind": "adaptation_proposal", "request_id": context["request_id"]}
        p = self._proposal(context)
        if s == "unsupported":
            p["operations"].insert(1, {"type": "delete_scene"})
        if s in ("wrong_maths", "wrong_twice"):
            p["claims"][0]["claimed"] = 5
        if s == "stale":
            p["scene_version"] = context["scene_version"] - 1
        return p

    def revise(self, context: dict[str, Any], instruction: dict[str, Any]) -> dict[str, Any]:
        p = self._proposal(context)
        if self.scenario == "wrong_twice":
            p["claims"][0]["claimed"] = 5
        return p


def _trace(events: list[dict[str, Any]], request_id: str, stage: str, status: str, **fields: Any) -> None:
    events.append({"event": "showloop.trace", "request_id": request_id, "stage": stage, "status": status, **fields})


def run_interruption(question: str = "Why is this slope instantaneous speed?", selected_object_id: str = "graph.tangent",
                     scenario: str = "success", request_id: str = "request-demo-001", telemetry: Telemetry | None = None) -> dict[str, Any]:
    """Runs the declared flow. The returned scene update is checked compiler input, not a renderer output."""
    session, events = Session(), []
    telemetry = telemetry or default_telemetry
    scene = session.lesson
    planner = MockPlanner(scenario)
    _trace(events, request_id, "interaction_capture", "received", lesson_id=scene["lesson_id"], node_id=scene["node_id"],
           scene_version=scene["scene_version"], selected_object_ids=[selected_object_id])
    if selected_object_id not in scene["objects"]:
        _trace(events, request_id, "selection_validation", "clarification", reason_code="unknown_scene_object")
        return {"status": "needs_clarification", "reason": "unknown_scene_object", "session": session, "events": events}
    context = {"request_id": request_id, "session_id": session.session_id, "lesson_id": scene["lesson_id"], "node_id": scene["node_id"],
               "scene_version": scene["scene_version"], "question_text": question, "selected_object_ids": [selected_object_id],
               "source_refs": scene["source_refs"], "deadline_ms": 10_000}
    _trace(events, request_id, "context_builder", "assembled", lesson_id=scene["lesson_id"], node_id=scene["node_id"],
           scene_version=scene["scene_version"], planner_id=planner.identifier, config_version=planner.config_version)

    def record(r):
        telemetry.verification(r)
        telemetry.tools(r.request_id, r.checked_claims)

    outcome = run_with_revision(planner, context, scene, on_result=record)
    for i, (attempt, ms) in enumerate(zip(outcome.attempts, outcome.planner_ms), start=1):
        _trace(events, request_id, "planner", "responded", attempt=i, elapsed_ms=round(ms, 3), planner_id=planner.identifier)
        _trace(events, request_id, "verification", attempt.status, attempt=i, reason_codes=attempt.reason_codes(),
               elapsed_ms=round(attempt.elapsed_ms, 3))
    final = outcome.final
    reason = final.reason_codes()[0] if final.reason_codes() else None

    if final.status == "needs_clarification":
        return {"status": "needs_clarification", "reason": "ambiguous_question", "clarification": final.clarification, "session": session, "events": events}
    if final.status in ("declined", "degraded"):
        _trace(events, request_id, "degradation", final.status, reason_code=reason, fallback=final.fallback["kind"])
        return {"status": "fallback", "reason": reason, "fallback": final.fallback, "session": session, "events": events}
    if final.status != "accepted":
        return {"status": "rejected", "reason": reason, "session": session, "events": events}

    update = final.scene_update
    anchor = update["return_anchor"]
    branch = {"branch_id": "branch-" + request_id, "status": "active", "return_anchor": anchor, "scene_update": update}
    session.branches.append(branch)
    scene["scene_version"] += 1
    _trace(events, request_id, "state_commit", "committed", transition="lesson_to_explanation_branch", return_anchor=anchor, scene_version=scene["scene_version"])
    branch["status"] = "completed"
    scene["node_id"] = anchor["node_id"]
    _trace(events, request_id, "resume", "completed", transition="explanation_branch_to_return_anchor", return_anchor=anchor, final_status="resumed")
    return {"status": "resumed", "reason": None, "scene_update": update, "session": session, "events": events}
