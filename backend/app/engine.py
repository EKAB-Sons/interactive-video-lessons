"""A deterministic, local-only demonstration of a checked lesson interruption."""
from __future__ import annotations
import copy
import time
from dataclasses import dataclass, field
from typing import Any

ALLOWED_OPERATIONS = {"highlight", "show_secant_sequence", "set_narration"}
SOURCE = "fixture:derivatives-tangent-v1"

class PlannerTimeout(Exception): pass

def lesson_fixture() -> dict[str, Any]:
    return {"lesson_id":"derivatives-intro-v1", "objective":"Relate tangent slope to instantaneous speed.",
      "node_id":"distance-time-tangent", "scene_version":7,
      "objects":{"graph.curve":{"kind":"curve"},"graph.tangent":{"kind":"line"},"graph.secant":{"kind":"line"}},
      "source_refs":[SOURCE]}

@dataclass
class Session:
    session_id: str = "session-demo-001"
    lesson: dict[str, Any] = field(default_factory=lesson_fixture)
    branches: list[dict[str, Any]] = field(default_factory=list)

class MockPlanner:
    identifier = "mock-planner"
    config_version = "mock-v1"
    def plan(self, context: dict[str, Any], scenario: str) -> dict[str, Any]:
        if scenario == "timeout": raise PlannerTimeout()
        if scenario == "ambiguous": return {"kind":"clarification", "request_id":context["request_id"], "status":"needs_clarification", "question":"Do you mean the tangent line or the distance-time curve?"}
        if scenario == "malformed": return {"kind":"adaptation_proposal", "request_id":context["request_id"]}
        op = "delete_scene" if scenario == "unsupported" else "show_secant_sequence"
        return {"kind":"adaptation_proposal", "request_id":context["request_id"], "planner_id":self.identifier,
          "config_version":self.config_version, "scene_version":context["scene_version"], "source_refs":[SOURCE],
          "return_anchor":{"node_id":context["node_id"], "scene_version":context["scene_version"]},
          "operations":[{"type":"highlight", "object_id":context["selected_object_ids"][0]},
            {"type":op, "object_id":"graph.tangent"},
            {"type":"set_narration", "text":"A secant approaches the tangent; its slope approaches instantaneous speed."}]}

def _trace(events: list[dict[str, Any]], request_id: str, stage: str, status: str, **fields: Any) -> None:
    events.append({"event":"interactive_video_lessons.trace", "request_id":request_id, "stage":stage, "status":status, **fields})

def _structural_error(p: dict[str, Any], request_id: str) -> str | None:
    required = {"kind","request_id","planner_id","config_version","scene_version","source_refs","return_anchor","operations"}
    if p.get("kind") != "adaptation_proposal": return "proposal_kind_invalid"
    if not required.issubset(p) or p.get("request_id") != request_id: return "proposal_contract_invalid"
    if not isinstance(p["operations"], list) or not isinstance(p["source_refs"], list): return "proposal_contract_invalid"
    return None

def run_interruption(question: str = "Why is this slope instantaneous speed?", selected_object_id: str = "graph.tangent", scenario: str = "success", request_id: str = "request-demo-001") -> dict[str, Any]:
    """Runs the declared flow. The returned scene update is not a renderer output."""
    session, events, planner = Session(), [], MockPlanner()
    scene = session.lesson
    _trace(events, request_id, "interaction_capture", "received", lesson_id=scene["lesson_id"], node_id=scene["node_id"], scene_version=scene["scene_version"], selected_object_ids=[selected_object_id])
    if selected_object_id not in scene["objects"]:
        _trace(events, request_id, "selection_validation", "clarification", reason_code="unknown_scene_object")
        return {"status":"needs_clarification", "reason":"unknown_scene_object", "session":session, "events":events}
    if scenario == "ambiguous":
        _trace(events, request_id, "context_builder", "assembled", scene_version=scene["scene_version"])
    context = {"request_id":request_id,"session_id":session.session_id,"lesson_id":scene["lesson_id"],"node_id":scene["node_id"],"scene_version":scene["scene_version"],"question_text":question,"selected_object_ids":[selected_object_id],"source_refs":scene["source_refs"]}
    _trace(events, request_id, "context_builder", "assembled", lesson_id=scene["lesson_id"], node_id=scene["node_id"], scene_version=scene["scene_version"], planner_id=planner.identifier, config_version=planner.config_version)
    started=time.perf_counter()
    try: proposal=planner.plan(copy.deepcopy(context), scenario)
    except PlannerTimeout:
        _trace(events, request_id, "planner", "fallback", reason_code="planner_timeout", elapsed_ms=round((time.perf_counter()-started)*1000,3))
        return {"status":"fallback", "reason":"planner_timeout", "session":session, "events":events}
    _trace(events, request_id, "planner", proposal["kind"], elapsed_ms=round((time.perf_counter()-started)*1000,3), planner_id=planner.identifier, config_version=planner.config_version)
    if proposal["kind"] == "clarification": return {"status":"needs_clarification", "reason":"ambiguous_question", "session":session, "events":events}
    err=_structural_error(proposal, request_id)
    if err:
        _trace(events, request_id, "contract_validation", "rejected", reason_code=err)
        return {"status":"rejected", "reason":err, "session":session, "events":events}
    bad = next((op for op in proposal["operations"] if op.get("type") not in ALLOWED_OPERATIONS or ("object_id" in op and op["object_id"] not in scene["objects"])), None)
    if bad:
        _trace(events, request_id, "operation_validation", "rejected", reason_code="operation_not_permitted", operation=bad.get("type"))
        return {"status":"rejected", "reason":"operation_not_permitted", "session":session, "events":events}
    if scenario == "stale": scene["scene_version"] += 1
    if proposal["scene_version"] != scene["scene_version"]:
        _trace(events, request_id, "freshness_check", "rejected", reason_code="stale_scene_version", active_scene_version=scene["scene_version"])
        return {"status":"rejected", "reason":"stale_scene_version", "session":session, "events":events}
    if any(ref not in scene["source_refs"] for ref in proposal["source_refs"]):
        _trace(events, request_id, "verification", "rejected", reason_code="unsupported_source_reference")
        return {"status":"rejected", "reason":"unsupported_source_reference", "session":session, "events":events}
    _trace(events, request_id, "verification", "accepted", verification_status="accepted")
    update={"kind":"scene_update", "base_scene_version":scene["scene_version"], "operations":proposal["operations"], "rendered":False}
    anchor=proposal["return_anchor"]; branch={"branch_id":"branch-"+request_id,"status":"active","return_anchor":anchor,"scene_update":update}
    session.branches.append(branch); scene["scene_version"] += 1
    _trace(events, request_id, "state_commit", "committed", transition="lesson_to_explanation_branch", return_anchor=anchor, scene_version=scene["scene_version"])
    branch["status"]="completed"; scene["node_id"]=anchor["node_id"]
    _trace(events, request_id, "resume", "completed", transition="explanation_branch_to_return_anchor", return_anchor=anchor, final_status="resumed")
    return {"status":"resumed", "reason":None, "scene_update":update, "session":session, "events":events}
