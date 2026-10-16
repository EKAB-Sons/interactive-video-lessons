"""Verification of a whole base lesson plan (Base Lesson Planning Engine output).

The same discipline as an adaptation proposal, applied node by node: each
node's claims are recomputed, its operations are checked against the scene as
it stands *after* the previous nodes, and narration may only state verified
values. Practice answers must point at a verified claim, so the planner never
supplies an answer key as free text.
"""
from __future__ import annotations

import time
from typing import Any

from .. import contracts
from . import grounding, maths, operations, structural
from .issues import Issue, IssueList
from .policy import MAX_ATTEMPTS, VERIFIER_VERSION, VerificationResult, build_revision_instruction
from .scene_sim import SceneSimulator


def verify_lesson_plan(plan: dict[str, Any], request: dict[str, Any]) -> VerificationResult:
    """`request` is the orchestrator's structured lesson request:
    {request_id, topic, approved_source_refs, ...}."""
    started = time.perf_counter()
    request_id = str(request.get("request_id", plan.get("request_id", "?")))
    attempt = plan.get("attempt", 1) if isinstance(plan, dict) else 1
    result = VerificationResult(request_id=request_id, status="rejected", attempt=attempt if attempt in (1, 2) else 1,
                                planner_id=plan.get("planner_id") if isinstance(plan, dict) else None,
                                config_version=plan.get("config_version") if isinstance(plan, dict) else None)
    issues = IssueList()

    def finish(status: str) -> VerificationResult:
        result.status = status
        result.issues = list(issues.items)
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        return result

    issues.extend(structural.check_schema("lesson_plan", plan))
    if not isinstance(plan, dict) or plan.get("kind") != "lesson_plan" or plan.get("request_id") != request_id:
        issues.add(Issue("request_id_mismatch", "plan does not answer this request", "/request_id", repairable=False))
        return finish("rejected")
    if plan.get("topic") != request.get("topic"):
        issues.add(Issue("topic_mismatch", f"plan topic {plan.get('topic')!r} differs from requested {request.get('topic')!r}", "/topic", repairable=False))
    pseudo_scene = {"topic": plan.get("topic", "")}
    issues.extend(structural.check_topic(pseudo_scene))
    if issues.has_unrepairable:
        return finish("rejected")
    if issues.has_blocking:  # schema problems: ask for a revision before deeper checks
        return _decide(issues, plan, request, {}, finish, result)

    approved = list(request.get("approved_source_refs", []))
    issues.extend(grounding.check_sources(plan["source_refs"], approved))

    sim = SceneSimulator({"objects": {k: {**v, "origin": "base"} for k, v in (plan.get("initial_objects") or {}).items()}})
    seen_nodes: set[str] = set()
    all_results: dict[str, Any] = {}
    compiled_nodes: list[dict[str, Any]] = []
    for n, node in enumerate(plan["nodes"]):
        path = f"/nodes/{n}"
        if node["node_id"] in seen_nodes:
            issues.add(Issue("duplicate_node_id", f"node id {node['node_id']} repeated", f"{path}/node_id"))
        seen_nodes.add(node["node_id"])
        claims_by_id = {str(c.get("id")): c for c in node["claims"]}
        claim_issues, claim_results = maths.check_claims(node["claims"], plan["topic"], base_path=f"{path}/claims")
        issues.extend(claim_issues)
        all_results.update({f"{node['node_id']}:{k}": v.as_dict() for k, v in claim_results.items()})
        op_issues, _ = operations.check_operations(node["operations"], sim, claims_by_id, plan["topic"], base_path=f"{path}/operations")
        issues.extend(op_issues)
        issues.extend(grounding.check_narrations(node["operations"], claims_by_id, sim.snapshot(), base_path=f"{path}/operations"))
        for i, practice in enumerate(node.get("practice", [])):
            r = claim_results.get(practice["claim_ref"])
            if r is None:
                issues.add(Issue("unknown_claim_ref", f"practice answer cites undeclared claim {practice['claim_ref']}", f"{path}/practice/{i}/claim_ref"))
            elif not r.ok:
                issues.add(Issue("practice_answer_unverified", f"practice answer depends on unverified claim {practice['claim_ref']}", f"{path}/practice/{i}/claim_ref"))
        if not issues.has_blocking:
            compiled = dict(node)
            compiled["operations"] = maths.substitute_verified_values(node["operations"], claim_results)
            compiled["practice"] = [{**p, "answer": claim_results[p["claim_ref"]].computed} for p in node.get("practice", [])]
            compiled_nodes.append(compiled)

    result.checked_claims = [{"id": k, **v} for k, v in all_results.items()]
    if not issues.has_blocking:
        result.scene_update = {
            "kind": "scene_update",
            "base_scene_version": 0,
            "operations": [op for node in compiled_nodes for op in node["operations"]],
            "return_anchor": {"node_id": plan["nodes"][0]["node_id"], "scene_version": 0},
            "rendered": False,
        }
        result.compiled_lesson = {"lesson_id": plan["lesson_id"], "topic": plan["topic"], "objective": plan["objective"],
                                  "nodes": compiled_nodes, "initial_objects": plan.get("initial_objects", {}),
                                  "source_refs": plan["source_refs"]}
        return finish("accepted")
    return _decide(issues, plan, request, all_results, finish, result)


def _decide(issues, plan, request, claim_results, finish, result):
    if issues.has_unrepairable:
        return finish("rejected")
    if result.attempt < MAX_ATTEMPTS:
        tspec = contracts.topic_spec(plan.get("topic", "")) or {}
        scene_like = {"scene_version": 0, "topic": plan.get("topic", ""), "objects": plan.get("initial_objects", {}) or {},
                      "source_refs": request.get("approved_source_refs", [])}
        result.revision_instruction = build_revision_instruction(issues, plan, scene_like, [])
        return finish("revision_requested")
    result.fallback = {"kind": "offer_wait_retry_return", "verified_claim_ids": [],
                       "text": "We could not verify a lesson from this material. You can try a narrower topic or different notes."}
    return finish("declined")
