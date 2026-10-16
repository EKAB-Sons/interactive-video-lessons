"""The Verification and Policy Layer's decision procedure.

verify_proposal() runs the check layers and maps the outcome onto product verdicts:

  issues                                   -> status
  ---------------------------------------- -> -------------------------------
  none blocking                            -> accepted (scene_update attached)
  any blocking & unrepairable              -> rejected (do not retry as-is)
  blocking, all repairable, attempt 1      -> revision_requested (+ instruction)
  blocking, all repairable, attempt 2      -> declined (+ checked fallback)
  planner returned clarification (valid)   -> needs_clarification
  planner returned failure                 -> declined (+ fallback)
  deadline already exceeded                -> degraded (+ fallback)

Warnings never change the status; they are recorded for review (M7).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .. import contracts
from . import grounding, maths, operations, structural
from .fallback import build_fallback
from .issues import Issue, IssueList, Severity
from .scene_sim import SceneSimulator

VERIFIER_VERSION = "verifier-v1"
MAX_ATTEMPTS = 2  # one automatic revision, then decline with a checked fallback


@dataclass
class VerificationResult:
    request_id: str
    status: str
    attempt: int
    issues: list[Issue] = field(default_factory=list)
    checked_claims: list[dict[str, Any]] = field(default_factory=list)
    scene_update: dict[str, Any] | None = None
    revision_instruction: dict[str, Any] | None = None
    clarification: dict[str, Any] | None = None
    fallback: dict[str, Any] | None = None
    compiled_lesson: dict[str, Any] | None = None   # lesson-plan verification only
    elapsed_ms: float = 0.0
    deadline_ms: int | None = None
    planner_id: str | None = None
    config_version: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def reason_codes(self) -> list[str]:
        out: list[str] = []
        for i in self.issues:
            if i.code not in out:
                out.append(i.code)
        return out

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "request_id": self.request_id,
            "status": self.status,
            "attempt": self.attempt,
            "verifier_version": VERIFIER_VERSION,
            "reason_codes": self.reason_codes(),
            "issues": [i.as_dict() for i in self.issues],
            "checked_claims": self.checked_claims,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }
        for key in ("scene_update", "revision_instruction", "clarification", "fallback", "deadline_ms", "planner_id", "config_version"):
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        return d


def _attempt(proposal: dict[str, Any]) -> int:
    a = proposal.get("attempt", 1)
    return a if isinstance(a, int) and 1 <= a <= MAX_ATTEMPTS else 1


def verify_proposal(
    proposal: dict[str, Any],
    context: dict[str, Any],
    scene: dict[str, Any],
    *,
    elapsed_before_ms: float = 0.0,
) -> VerificationResult:
    """Decide on one planner response. `elapsed_before_ms` is the time already
    spent on this request (capture + planning) so the deadline check reflects
    the student's wait, not just verification time."""
    started = time.perf_counter()
    request_id = str(context.get("request_id", proposal.get("request_id", "?")))
    attempt = _attempt(proposal) if isinstance(proposal, dict) else 1
    result = VerificationResult(request_id=request_id, status="rejected", attempt=attempt,
                                deadline_ms=context.get("deadline_ms"),
                                planner_id=proposal.get("planner_id") if isinstance(proposal, dict) else None,
                                config_version=proposal.get("config_version") if isinstance(proposal, dict) else None)
    issues = IssueList()

    def finish(status: str) -> VerificationResult:
        result.status = status
        result.issues = list(issues.items)
        result.elapsed_ms = elapsed_before_ms + (time.perf_counter() - started) * 1000
        return result

    # Deadline first: a correct answer after the budget is still a failed experience.
    deadline = context.get("deadline_ms")
    if isinstance(deadline, int) and elapsed_before_ms > deadline:
        issues.add(Issue("deadline_exceeded", f"{elapsed_before_ms:.0f} ms elapsed against a {deadline} ms budget", "/",
                         repairable=False, layer="policy"))
        result.fallback = build_fallback({}, context, reason="deadline")
        return finish("degraded")

    # Shape: which of the three typed responses is this?
    schema_issues = structural.check_schema("adaptation_plan", proposal)
    kind = proposal.get("kind") if isinstance(proposal, dict) else None
    if kind == "clarification" and not schema_issues:
        return _handle_clarification(proposal, context, scene, issues, finish, result)
    if kind == "failure" and not schema_issues:
        issues.add(Issue(f"planner_{proposal['status']}", proposal.get("reason", ""), "/", repairable=False, layer="policy"))
        result.fallback = build_fallback({}, context, reason=proposal["status"])
        return finish("declined")
    if schema_issues:
        issues.extend(schema_issues)
        # A proposal whose kind we cannot recognise cannot be revised meaningfully.
        if kind not in ("adaptation_proposal", "clarification", "failure") or proposal.get("request_id") != request_id:
            return finish("rejected")
        # Still check binding, so a stale proposal is rejected rather than granted a pointless revision.
        issues.extend(structural.check_topic(scene))
        issues.extend(structural.check_binding(proposal, context, scene))
        return _decide_repairable(issues, proposal, context, scene, {}, {}, [], finish, result)

    # Binding and scope: unrepairable, so they end the matter early.
    issues.extend(structural.check_topic(scene))
    issues.extend(structural.check_binding(proposal, context, scene))
    if issues.has_unrepairable:
        return finish("rejected")
    issues.extend(structural.check_interpretation(proposal, context, scene))
    issues.extend(grounding.check_sources(proposal["source_refs"], scene.get("source_refs", [])))

    # Mathematics: recompute every claim.
    claims_by_id = {str(c.get("id")): c for c in proposal["claims"]}
    claim_issues, claim_results = maths.check_claims(proposal["claims"], scene["topic"])
    issues.extend(claim_issues)
    result.checked_claims = [r.as_dict() for r in claim_results.values()]

    # Operations against the simulated scene, then narration discipline.
    sim = SceneSimulator(scene)
    op_issues, passed = operations.check_operations(proposal["operations"], sim, claims_by_id, scene["topic"])
    issues.extend(op_issues)
    issues.extend(grounding.check_narrations(proposal["operations"], claims_by_id, sim.snapshot() | scene.get("objects", {})))

    # Any operation that leans on an unverified claim fails even if its own arguments were fine.
    for i, op in enumerate(proposal["operations"]):
        cref = op.get("claim_ref")
        if cref and cref in claim_results and not claim_results[cref].ok and i in passed:
            passed.remove(i)
        for m in grounding.PLACEHOLDER.finditer(str(op.get("text", "")) + str(op.get("label_text", ""))):
            if m.group(1) in claim_results and not claim_results[m.group(1)].ok and i in passed:
                passed.remove(i)

    if not issues.has_blocking:
        result.scene_update = {
            "kind": "scene_update",
            "base_scene_version": scene["scene_version"],
            "operations": maths.substitute_verified_values(proposal["operations"], claim_results),
            "return_anchor": proposal["return_anchor"],
            "rendered": False,
        }
        return finish("accepted")
    return _decide_repairable(issues, proposal, context, scene, claim_results, claims_by_id, passed, finish, result)


def _handle_clarification(proposal, context, scene, issues, finish, result):
    candidates = proposal.get("candidate_object_ids") or []
    known = [c for c in candidates if c in scene.get("objects", {})]
    for i, c in enumerate(candidates):
        if c not in scene.get("objects", {}):
            issues.add(Issue("unknown_candidate_object", f"{c!r} is not in the scene", f"/candidate_object_ids/{i}",
                             severity=Severity.WARNING, layer="structural"))
    if proposal.get("request_id") != result.request_id:
        issues.add(Issue("request_id_mismatch", "clarification answers a different request", "/request_id", repairable=False))
        return finish("rejected")
    if grounding._MARKERS.search(proposal["question"]):
        issues.add(Issue("instruction_marker_in_output", "clarification text carries an instruction marker", "/question", repairable=False, layer="grounding"))
        return finish("rejected")
    # The student is only ever shown candidates that exist; the question is passed through as typed.
    result.clarification = {"question": proposal["question"], "candidate_object_ids": known or list(context.get("selected_object_ids") or [])}
    return finish("needs_clarification")


def _decide_repairable(issues, proposal, context, scene, claim_results, claims_by_id, passed, finish, result):
    if issues.has_unrepairable:
        return finish("rejected")
    if result.attempt < MAX_ATTEMPTS:
        result.revision_instruction = build_revision_instruction(issues, proposal, scene, passed)
        return finish("revision_requested")
    result.fallback = build_fallback(claim_results, context, reason="revision_failed", claims_by_id=claims_by_id)
    return finish("declined")


def build_revision_instruction(issues: IssueList, proposal: dict[str, Any], scene: dict[str, Any], passed: list[int]) -> dict[str, Any]:
    tspec = contracts.topic_spec(scene.get("topic", "")) or {}
    instruction = {
        "kind": "revision_instruction",
        "request_id": proposal.get("request_id"),
        "attempt": 2,
        "failed_checks": [
            {"code": i.code, "path": i.path, "message": i.message, **({"computed": i.computed} if i.computed is not None else {})}
            for i in issues.blocking
        ],
        "constraints": {
            "scene_version": scene["scene_version"],
            "allowed_operations": list(tspec.get("allowed_operations", [])),
            "known_object_ids": sorted(scene.get("objects", {})),
            "approved_source_refs": list(scene.get("source_refs", [])),
            "allowed_claim_types": list(tspec.get("allowed_claim_types", [])),
            "keep_operation_indices": sorted(passed),
        },
    }
    assert contracts.validation_errors("revision_instruction", instruction) == [], "verifier emitted an invalid instruction"
    return instruction
