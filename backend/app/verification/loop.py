"""The one-revision loop.

    propose -> verify -> accepted?            done
                      -> revision_requested?  revise once -> verify -> done
                      -> anything else        done

The loop owns the clock: it measures time spent in the planner so the deadline
check in verify_proposal() sees the student's real wait. The planner is any
callable; the loop never inspects its internals, which is the point of the
boundary.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .fallback import build_fallback
from .issues import Issue
from .policy import MAX_ATTEMPTS, VerificationResult, verify_proposal


class Planner(Protocol):
    def plan(self, context: dict[str, Any]) -> dict[str, Any]: ...
    def revise(self, context: dict[str, Any], instruction: dict[str, Any]) -> dict[str, Any]: ...


class PlannerTimeout(Exception):
    pass


@dataclass
class LoopOutcome:
    final: VerificationResult
    attempts: list[VerificationResult] = field(default_factory=list)
    planner_ms: list[float] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.final.status


def _timed(fn: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any] | None, float, Exception | None]:
    t0 = time.perf_counter()
    try:
        return fn(), (time.perf_counter() - t0) * 1000, None
    except Exception as exc:  # the planner is untrusted; any exception is a planner failure, never ours
        return None, (time.perf_counter() - t0) * 1000, exc


def run_with_revision(planner: Planner, context: dict[str, Any], scene: dict[str, Any], *,
                      elapsed_before_ms: float = 0.0, on_result: Callable[[VerificationResult], None] | None = None) -> LoopOutcome:
    attempts: list[VerificationResult] = []
    planner_ms: list[float] = []
    elapsed = elapsed_before_ms

    proposal, ms, exc = _timed(lambda: planner.plan(context))
    planner_ms.append(ms)
    elapsed += ms
    if exc is not None:
        result = _planner_failure(context, exc, attempt=1, elapsed=elapsed)
        if on_result:
            on_result(result)
        return LoopOutcome(final=result, attempts=[result], planner_ms=planner_ms)

    result = verify_proposal(proposal, context, scene, elapsed_before_ms=elapsed)
    attempts.append(result)
    if on_result:
        on_result(result)
    if result.status != "revision_requested":
        return LoopOutcome(final=result, attempts=attempts, planner_ms=planner_ms)

    revised, ms, exc = _timed(lambda: planner.revise(context, result.revision_instruction))
    planner_ms.append(ms)
    elapsed = result.elapsed_ms + ms
    if exc is not None:
        final = _planner_failure(context, exc, attempt=2, elapsed=elapsed)
    else:
        if isinstance(revised, dict):
            revised = {**revised, "attempt": MAX_ATTEMPTS}  # the verifier, not the planner, decides which attempt this is
        final = verify_proposal(revised, context, scene, elapsed_before_ms=elapsed)
        if final.status == "revision_requested":  # cannot happen with attempt forced to 2, but never loop
            final.status = "declined"
    attempts.append(final)
    if on_result:
        on_result(final)
    return LoopOutcome(final=final, attempts=attempts, planner_ms=planner_ms)


def _planner_failure(context: dict[str, Any], exc: Exception, *, attempt: int, elapsed: float) -> VerificationResult:
    reason = "timeout" if isinstance(exc, (PlannerTimeout, TimeoutError)) else "provider_error"
    result = VerificationResult(request_id=str(context.get("request_id")), status="declined", attempt=attempt,
                                deadline_ms=context.get("deadline_ms"))
    result.issues = [Issue(f"planner_{reason}", f"{type(exc).__name__}", "/", repairable=False, layer="policy")]
    result.fallback = build_fallback({}, context, reason=reason)
    result.elapsed_ms = elapsed
    return result
