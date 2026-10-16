"""Held-out request evaluation for contextual response quality.

A case is one student request with everything the verifier needs: context,
scene, and the planner's recorded attempts. Recording the planner output makes
the evaluation reproducible and model-independent: re-running it exercises the
verifier, not the network. A live planner can be substituted through the same
Planner protocol when the FM interface lands.

Scoring rule: an in-scope request succeeds only when the final verdict
is `accepted`. Clarifications, declines, degradations and rejections on in-scope
requests are failures, so withholding answers cannot inflate the pass rate.
Out-of-scope requests succeed when the system withholds (anything but accepted);
they are reported separately and never enter the 90/100 denominator.

Leakage guard: cases carry a `group_id` (source passage / conversation family).
Held-out groups must not appear in the development manifest, and exact
duplicates inside the held-out set are rejected.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..verification import run_with_revision
from ..verification.loop import Planner, PlannerTimeout

TARGET_PASS = 90
TARGET_TOTAL = 100


@dataclass
class Case:
    case_id: str
    group_id: str
    in_scope: bool
    context: dict[str, Any]
    scene: dict[str, Any]
    attempts: list[dict[str, Any] | str]   # recorded planner outputs; the string "timeout" simulates a planner timeout
    notes: str = ""

    def fingerprint(self) -> str:
        body = json.dumps({"q": self.context.get("question_text"), "sel": self.context.get("selected_object_ids"),
                           "scene": self.scene.get("lesson_id"), "node": self.scene.get("node_id")}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()[:16]


class RecordedPlanner:
    def __init__(self, attempts: list[dict[str, Any] | str]) -> None:
        self._attempts = list(attempts)

    def _next(self) -> dict[str, Any]:
        if not self._attempts:
            raise PlannerTimeout("no recorded attempt left")
        nxt = self._attempts.pop(0)
        if nxt == "timeout":
            raise PlannerTimeout()
        return nxt

    def plan(self, context):
        return self._next()

    def revise(self, context, instruction):
        return self._next()


def load_cases(path: Path) -> list[Case]:
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            cases.append(Case(d["case_id"], d["group_id"], d["in_scope"], d["context"], d["scene"], d["attempts"], d.get("notes", "")))
    return cases


@dataclass
class CaseOutcome:
    case_id: str
    in_scope: bool
    final_status: str
    reason_codes: list[str]
    attempts: int
    success: bool
    elapsed_ms: float


@dataclass
class HeldoutReport:
    outcomes: list[CaseOutcome] = field(default_factory=list)
    leakage: list[str] = field(default_factory=list)

    @property
    def in_scope(self) -> list[CaseOutcome]:
        return [o for o in self.outcomes if o.in_scope]

    @property
    def out_of_scope(self) -> list[CaseOutcome]:
        return [o for o in self.outcomes if not o.in_scope]

    @property
    def passed(self) -> int:
        return sum(o.success for o in self.in_scope)

    @property
    def pass_rate(self) -> float:
        return self.passed / len(self.in_scope) if self.in_scope else 0.0

    def meets_target(self) -> bool:
        """90/100 means a 0.90 rate; with fewer than 100 cases the rate is reported but the target is not claimed."""
        return len(self.in_scope) >= TARGET_TOTAL and self.pass_rate >= TARGET_PASS / TARGET_TOTAL and not self.leakage

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for o in self.in_scope:
            counts[o.final_status] = counts.get(o.final_status, 0) + 1
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "in_scope_total": len(self.in_scope), "in_scope_passed": self.passed, "pass_rate": round(self.pass_rate, 4),
            "target": f"{TARGET_PASS}/{TARGET_TOTAL}", "meets_target": self.meets_target(),
            "enough_cases_for_claim": len(self.in_scope) >= TARGET_TOTAL,
            "in_scope_status_counts": self.status_counts(),
            "out_of_scope_total": len(self.out_of_scope),
            "out_of_scope_correctly_withheld": sum(o.success for o in self.out_of_scope),
            "leakage": self.leakage,
            "failures": [{"case_id": o.case_id, "status": o.final_status, "reason_codes": o.reason_codes}
                         for o in self.outcomes if not o.success],
        }


def check_leakage(heldout: Iterable[Case], dev: Iterable[Case] = ()) -> list[str]:
    problems = []
    dev_groups = {c.group_id for c in dev}
    seen: dict[str, str] = {}
    for c in heldout:
        if c.group_id in dev_groups:
            problems.append(f"{c.case_id}: group {c.group_id!r} also appears in the development set")
        fp = c.fingerprint()
        if fp in seen:
            problems.append(f"{c.case_id}: exact duplicate of {seen[fp]}")
        seen.setdefault(fp, c.case_id)
    return problems


def run_heldout(cases: list[Case], dev_cases: list[Case] = (), *, planner_factory=None, on_result=None) -> HeldoutReport:
    """planner_factory(case) -> Planner lets a live planner replace the recording."""
    report = HeldoutReport(leakage=check_leakage(cases, dev_cases))
    for case in cases:
        planner: Planner = planner_factory(case) if planner_factory else RecordedPlanner(case.attempts)
        outcome = run_with_revision(planner, case.context, case.scene, on_result=on_result)
        final = outcome.final
        accepted = final.status == "accepted"
        report.outcomes.append(CaseOutcome(case.case_id, case.in_scope, final.status, final.reason_codes(), len(outcome.attempts),
                                           success=accepted if case.in_scope else not accepted, elapsed_ms=final.elapsed_ms))
    return report
