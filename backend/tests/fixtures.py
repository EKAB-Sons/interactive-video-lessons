"""Shared, hand-authored fixtures for the derivatives topic.

Everything here is team-authored content; nothing comes from a student. The
scene is the standard derivatives demo (distance–time graph with a tangent),
extended with the fields the verifier needs: topic, node list, curve expression.
"""
from __future__ import annotations

import copy
from typing import Any

SOURCE = "fixture:derivatives-tangent-v1"


def scene_fixture() -> dict[str, Any]:
    return {
        "lesson_id": "derivatives-intro-v1",
        "node_id": "distance-time-tangent",
        "scene_version": 7,
        "topic": "derivatives",
        "objective": "Relate tangent slope to instantaneous speed.",
        "nodes": ["intro", "distance-time-tangent", "secant-limit", "summary"],
        "objects": {
            "graph.axes": {"kind": "axis", "origin": "base"},
            "graph.curve": {"kind": "curve", "expression": "t**2", "var": "t", "domain": [0, 4], "origin": "base"},
            "graph.tangent": {"kind": "line", "curve": "graph.curve", "at_x": 2, "origin": "base"},
            "graph.secant": {"kind": "line", "origin": "base"},
            "label.title": {"kind": "label", "origin": "base"},
        },
        "source_refs": [SOURCE],
    }


def context_packet_fixture(**overrides: Any) -> dict[str, Any]:
    packet = {
        "request_id": "request-demo-001",
        "session_id": "session-demo-001",
        "lesson_id": "derivatives-intro-v1",
        "node_id": "distance-time-tangent",
        "scene_version": 7,
        "question_text": "Why is the slope of this line the instantaneous speed?",
        "question_modality": "text",
        "selected_object_ids": ["graph.tangent"],
        "source_refs": [SOURCE],
        "retrieved_passages": [
            {"source_ref": SOURCE, "role": "source_data",
             "text": "The derivative of s(t) at t = a is the limit of the secant slopes (s(a+h) - s(a))/h as h tends to 0."}
        ],
        "conversation": [],
        "deadline_ms": 10000,
    }
    packet.update(overrides)
    return packet


def proposal_fixture(**overrides: Any) -> dict[str, Any]:
    """A correct proposal: a secant closing onto the tangent at t = 2 on s = t^2."""
    proposal = {
        "kind": "adaptation_proposal",
        "request_id": "request-demo-001",
        "attempt": 1,
        "planner_id": "mock-planner",
        "config_version": "mock-v2",
        "scene_version": 7,
        "interpretation": {
            "question_summary": "Why the tangent's slope at t = 2 equals the instantaneous speed.",
            "referents": ["graph.tangent"],
        },
        "source_refs": [SOURCE],
        "claims": [
            {"id": "c1", "type": "slope_tangent", "expression": "t**2", "var": "t", "at_x": 2, "claimed": 4},
            {"id": "c2", "type": "secant_converges", "expression": "t**2", "var": "t", "at_x": 2, "h_values": [1, 0.5, 0.1, 0.01]},
            {"id": "c3", "type": "slope_secant", "expression": "t**2", "var": "t", "at_x": 2, "h": 1, "claimed": 5},
        ],
        "operations": [
            {"type": "highlight", "object_id": "graph.tangent"},
            {"type": "show_secant_sequence", "curve": "graph.curve", "at_x": 2, "h_values": [1, 0.5, 0.1, 0.01], "claim_ref": "c2"},
            {"type": "annotate_value", "object_id": "label.slope", "anchor": "graph.tangent",
             "label_text": "slope = {{claim:c1}}", "claim_ref": "c1"},
            {"type": "set_narration",
             "text": "As h shrinks, the secant slope approaches {{claim:c1}}, the slope of the tangent, which is the instantaneous speed at that moment."},
        ],
        "return_anchor": {"node_id": "distance-time-tangent", "scene_version": 7},
    }
    proposal.update(overrides)
    return proposal


def lesson_plan_fixture() -> dict[str, Any]:
    return {
        "kind": "lesson_plan",
        "request_id": "lesson-request-001",
        "attempt": 1,
        "planner_id": "mock-base-planner",
        "config_version": "mock-v1",
        "lesson_id": "derivatives-intro-v2",
        "topic": "derivatives",
        "objective": "Relate tangent slope to instantaneous speed.",
        "source_refs": [SOURCE],
        "initial_objects": {
            "graph.axes": {"kind": "axis"},
            "graph.curve": {"kind": "curve", "expression": "t**2", "var": "t", "domain": [0, 4]},
        },
        "nodes": [
            {
                "node_id": "intro",
                "title": "Distance against time",
                "claims": [],
                "operations": [
                    {"type": "highlight", "object_id": "graph.curve"},
                    {"type": "set_narration", "text": "This curve shows distance against time for a ball rolling down a ramp."},
                ],
            },
            {
                "node_id": "tangent-at-two",
                "title": "The tangent at t = 2",
                "claims": [{"id": "c1", "type": "slope_tangent", "expression": "t**2", "var": "t", "at_x": 2, "claimed": 4}],
                "operations": [
                    {"type": "draw_tangent", "object_id": "graph.tangent", "curve": "graph.curve", "at_x": 2, "claim_ref": "c1"},
                    {"type": "annotate_value", "object_id": "label.slope", "anchor": "graph.tangent", "label_text": "slope = {{claim:c1}}", "claim_ref": "c1"},
                    {"type": "set_narration", "text": "The tangent at this instant has slope {{claim:c1}}: the instantaneous speed."},
                ],
                "practice": [{"prompt": "What is the instantaneous speed at t = 2?", "claim_ref": "c1"}],
            },
        ],
    }


def deep(obj: Any) -> Any:
    return copy.deepcopy(obj)
