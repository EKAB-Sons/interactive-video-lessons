"""Check layer 1: structure and binding.

Does the proposal have the shape the contract requires, and is it bound to the
request and scene state it claims to answer? Everything here is cheap and most
failures are unrepairable, so it runs first.
"""
from __future__ import annotations

from typing import Any

from .. import contracts
from .issues import Issue, Severity

LAYER = "structural"


def check_schema(schema_name: str, instance: Any) -> list[Issue]:
    errors = contracts.plan_validation_errors(instance) if schema_name == "adaptation_plan" else contracts.validation_errors(schema_name, instance)
    return [
        Issue(code="schema_violation", message=err["message"], path=err["path"], layer=LAYER,
              # A missing field or wrong type can be revised; an entirely wrong kind cannot.
              repairable=err["validator"] not in ("const", "oneOf"))
        for err in errors
    ]


def check_binding(proposal: dict[str, Any], context: dict[str, Any], scene: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    # Absent fields are schema violations (repairable); only *present but wrong* bindings are unrepairable.
    if "request_id" in proposal and proposal["request_id"] != context.get("request_id"):
        issues.append(Issue("request_id_mismatch", "proposal answers a different request", "/request_id",
                            repairable=False, layer=LAYER))
    if "scene_version" in proposal and proposal["scene_version"] != scene.get("scene_version"):
        issues.append(Issue("stale_scene_version",
                            f"proposal built against scene version {proposal.get('scene_version')} but live version is {scene.get('scene_version')}",
                            "/scene_version", repairable=False, layer=LAYER))
    if context.get("scene_version") != scene.get("scene_version"):
        issues.append(Issue("stale_context", "context packet predates the live scene; rebuild context", "/",
                            repairable=False, layer=LAYER))
    anchor = proposal.get("return_anchor") or {}
    nodes = scene.get("nodes") or [scene.get("node_id")]
    if "node_id" in anchor and anchor["node_id"] not in nodes:
        issues.append(Issue("unknown_return_anchor", f"return anchor {anchor.get('node_id')!r} is not a lesson node",
                            "/return_anchor/node_id", layer=LAYER))
    if anchor.get("scene_version") is not None and anchor.get("scene_version") > scene.get("scene_version", 0):
        issues.append(Issue("return_anchor_in_future", "return anchor names a scene version that does not exist yet",
                            "/return_anchor/scene_version", layer=LAYER))
    return issues


def check_topic(scene: dict[str, Any]) -> list[Issue]:
    spec = contracts.topic_spec(scene.get("topic", ""))
    if spec is None:
        return [Issue("topic_out_of_scope", f"topic {scene.get('topic')!r} is not in the bounded topic set", "/topic",
                      repairable=False, layer=LAYER)]
    if spec["status"] != "implemented":
        return [Issue("topic_deferred", f"topic {scene.get('topic')!r} is declared but not implemented", "/topic",
                      repairable=False, layer=LAYER)]
    return []


def check_interpretation(proposal: dict[str, Any], context: dict[str, Any], scene: dict[str, Any]) -> list[Issue]:
    """The planner's referents must be real objects, and if the student selected
    something, the planner must have acknowledged it (or asked to clarify)."""
    issues: list[Issue] = []
    referents = (proposal.get("interpretation") or {}).get("referents", [])
    objects = scene.get("objects", {})
    for i, ref in enumerate(referents):
        if ref not in objects:
            issues.append(Issue("unknown_referent", f"referent {ref!r} is not in the scene", f"/interpretation/referents/{i}", layer=LAYER))
    selected = context.get("selected_object_ids") or []
    if selected and not set(selected) & set(referents):
        issues.append(Issue("selection_ignored",
                            f"student selected {selected} but the interpretation does not mention any of them",
                            "/interpretation/referents", layer=LAYER))
    return issues
