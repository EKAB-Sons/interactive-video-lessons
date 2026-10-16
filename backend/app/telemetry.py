"""Monitoring hooks owned by verification: M2 (content safety), M6 (tools), M7 (verification).

One event shape for every hook so the observability wiring (App/orchestration
owner) can route them without special cases:

    {"hook": "M7", "event": "verification.decision", "ts": ..., "request_id": ...,
     "status": ..., "reason_codes": [...], "elapsed_ms": ..., "verifier_version": ..., ...}

Events go to a sink. The default sink appends JSON lines to a file (or stdout);
tests install an in-memory sink. Nothing here blocks the request path: a
failing sink is logged and swallowed, except for the fail-closed guard used by
the service when audit logging is mandatory.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

HOOKS = {
    "M2": "Content ingestion and safety: extraction success, source coverage, malicious-content detection",
    "M6": "Retrieval and mathematical tools: retrieval grounding, solver completion, tool-result consistency",
    "M7": "Verification and policy layer: incorrect plans caught, correct plans passed, repair success, retry intent",
}


class Sink(Protocol):
    def write(self, event: dict[str, Any]) -> None: ...


@dataclass
class MemorySink:
    events: list[dict[str, Any]] = field(default_factory=list)

    def write(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def by_hook(self, hook: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["hook"] == hook]


@dataclass
class JsonlSink:
    path: Path | None = None   # None -> stdout

    def write(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, sort_keys=True, default=str)
        if self.path is None:
            sys.stdout.write(line + "\n")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


class Telemetry:
    def __init__(self, sink: Sink | None = None, *, fail_closed: bool = False) -> None:
        self.sink: Sink = sink or MemorySink()
        self.fail_closed = fail_closed
        self.dropped = 0

    def emit(self, hook: str, event: str, **fields: Any) -> dict[str, Any]:
        if hook not in HOOKS:
            raise ValueError(f"unknown hook {hook}; verification owns {sorted(HOOKS)}")
        record = {"hook": hook, "event": event, "ts": time.time(), **fields}
        try:
            self.sink.write(record)
        except Exception:
            self.dropped += 1
            if self.fail_closed:
                raise
        return record

    # Convenience emitters so call sites stay one line and field names stay consistent.
    def verification(self, result: Any, *, planner_ms: float | None = None) -> dict[str, Any]:
        return self.emit("M7", "verification.decision", request_id=result.request_id, status=result.status,
                         attempt=result.attempt, reason_codes=result.reason_codes(), elapsed_ms=round(result.elapsed_ms, 3),
                         planner_ms=planner_ms, verifier_version=_verifier_version(), planner_id=result.planner_id,
                         config_version=result.config_version, deadline_ms=result.deadline_ms,
                         blocking_issues=sum(1 for i in result.issues if i.severity.value == "blocking"),
                         warnings=sum(1 for i in result.issues if i.severity.value == "warning"),
                         claims_total=len(result.checked_claims),
                         claims_verified=sum(1 for c in result.checked_claims if c.get("status") == "verified"))

    def tools(self, request_id: str, checked_claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One M6 event per claim: solver completion and tool-result consistency are per-claim facts."""
        return [self.emit("M6", "tools.claim", request_id=request_id, claim_id=c.get("id"), claim_type=c.get("type"),
                          status=c.get("status"), solver_version=c.get("solver_version")) for c in checked_claims]

    # Read-side helpers for tests and the /telemetry/recent endpoint (in-memory sink only).
    def events(self, hook: str | None = None, request_id: str | None = None) -> list[dict[str, Any]]:
        if not isinstance(self.sink, MemorySink):
            return []
        return [e for e in self.sink.events if (hook is None or e["hook"] == hook)
                and (request_id is None or e.get("request_id") == request_id)]

    def clear(self) -> None:
        if isinstance(self.sink, MemorySink):
            self.sink.events.clear()

    def safety(self, source_ref: str, decisions: list[Any]) -> dict[str, Any]:
        counts = {"admitted": 0, "flagged": 0, "quarantined": 0}
        for d in decisions:
            counts[d.decision] += 1
        return self.emit("M2", "safety.admission", source_ref=source_ref, **counts,
                         max_score=max((d.report["injection_score"] for d in decisions), default=0.0))


def _verifier_version() -> str:
    from .verification.policy import VERIFIER_VERSION
    return VERIFIER_VERSION


telemetry = Telemetry(MemorySink())   # process-wide default; the engine and tests share it
