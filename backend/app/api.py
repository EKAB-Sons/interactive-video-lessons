"""HTTP surface for the Verification and Policy Layer, the tools and the safety scan.

The orchestrator (App/orchestration owner) calls these over the network in the
deployed slice. The service is stateless: every request carries the scene,
context and proposal it should be judged against, so a stale state cannot hide
in the verifier. Audit logging is fail-closed: if the telemetry sink cannot be
written, /verify answers 503 rather than silently accepting a plan nobody can
later investigate if audit logging is unavailable.

Run locally:  uvicorn app.api:app --reload
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import contracts
from .safety import CanaryRegistry, admit_passages, leak_check, scan_passage
from .telemetry import JsonlSink, MemorySink, Telemetry
from .tools import solver
from .verification import VERIFIER_VERSION, verify_lesson_plan, verify_proposal

_sink_path = os.environ.get("IVL_TELEMETRY_PATH")
telemetry = Telemetry(JsonlSink(Path(_sink_path)) if _sink_path else MemorySink(), fail_closed=True)
canaries = CanaryRegistry()
for token in filter(None, os.environ.get("IVL_CANARIES", "").split(",")):
    canaries.plant(token.strip())

app = FastAPI(title="IVL Verification and Policy Layer", version=VERIFIER_VERSION)


class VerifyRequest(BaseModel):
    proposal: dict[str, Any]
    context: dict[str, Any]
    scene: dict[str, Any]
    elapsed_before_ms: float = Field(0.0, ge=0)
    planner_ms: float | None = None


class LessonVerifyRequest(BaseModel):
    plan: dict[str, Any]
    request: dict[str, Any]


class SolveRequest(BaseModel):
    claims: list[dict[str, Any]]
    topic: str = "derivatives"


class ScanRequest(BaseModel):
    passages: list[dict[str, str]]   # [{passage_id, source_ref, text}]


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "verifier_version": VERIFIER_VERSION, "solver_version": solver.SOLVER_VERSION,
            "operations_registry": contracts.operations_registry()["registry_version"],
            "topics_registry": contracts.topics_registry()["registry_version"], "telemetry_dropped": telemetry.dropped}


@app.get("/contracts/{name}")
def get_contract(name: str) -> dict[str, Any]:
    if name == "operations":
        return contracts.operations_registry()
    if name == "topics":
        return contracts.topics_registry()
    try:
        return contracts.schema(name)
    except KeyError:
        raise HTTPException(404, f"unknown contract {name}")


@app.post("/verify")
def verify(req: VerifyRequest) -> dict[str, Any]:
    leaks = leak_check(req.proposal, canaries)
    result = verify_proposal(req.proposal, req.context, req.scene, elapsed_before_ms=req.elapsed_before_ms)
    if leaks:
        result.issues = leaks + result.issues
        result.status = "rejected"
        result.scene_update = result.revision_instruction = None
    try:
        telemetry.verification(result, planner_ms=req.planner_ms)
        if result.checked_claims:
            telemetry.tools(result.request_id, result.checked_claims)
    except Exception:
        raise HTTPException(503, "audit log unavailable; refusing to decide without a record")
    return result.as_dict()


@app.post("/verify/lesson")
def verify_lesson(req: LessonVerifyRequest) -> dict[str, Any]:
    result = verify_lesson_plan(req.plan, req.request)
    try:
        telemetry.verification(result)
    except Exception:
        raise HTTPException(503, "audit log unavailable; refusing to decide without a record")
    out = result.as_dict()
    if result.compiled_lesson is not None:
        out["compiled_lesson"] = result.compiled_lesson
    return out


@app.post("/tools/solve")
def solve(req: SolveRequest) -> dict[str, Any]:
    tspec = contracts.topic_spec(req.topic)
    if tspec is None:
        raise HTTPException(400, f"topic {req.topic!r} is not in the bounded set")
    results = [solver.solve_claim(c, tspec["allowed_functions"]).as_dict() for c in req.claims]
    telemetry.tools("tools-call", results)
    return {"solver_version": solver.SOLVER_VERSION, "results": results}


@app.post("/safety/scan")
def scan(req: ScanRequest) -> dict[str, Any]:
    decisions = admit_passages([(p["passage_id"], p["source_ref"], p["text"]) for p in req.passages])
    for ref in {p["source_ref"] for p in req.passages}:
        telemetry.safety(ref, [d for d in decisions if d.passage.source_ref == ref])
    return {"decisions": [{"passage_id": d.passage.passage_id, "decision": d.decision, "report": d.report} for d in decisions]}


@app.get("/telemetry/recent")
def recent(limit: int = 50) -> dict[str, Any]:
    return {"events": telemetry.events()[-limit:],
            "note": "only the in-memory sink is readable here; the JSONL sink is read by the observability stack"}
