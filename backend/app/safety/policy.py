"""Admission policy for passages entering the Approved Knowledge Base.

Three bands:
  score >= QUARANTINE_THRESHOLD  -> quarantined: never retrieved, never sent to a planner
  WARN_THRESHOLD <= score < Q    -> admitted but flagged for human review (M2 signal)
  score < WARN_THRESHOLD         -> admitted
Every passage, admitted or not, keeps its SafetyReport, so the decision is auditable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..tools.retrieval import Passage
from .scan import scan_passage

QUARANTINE_THRESHOLD = 0.5
WARN_THRESHOLD = 0.3


@dataclass
class AdmissionDecision:
    passage: Passage
    decision: str   # admitted | flagged | quarantined
    report: dict[str, Any]


def admit_passages(raw: Iterable[tuple[str, str, str]]) -> list[AdmissionDecision]:
    """raw: iterable of (passage_id, source_ref, text). Returns decisions in order."""
    out: list[AdmissionDecision] = []
    for passage_id, source_ref, text in raw:
        report = scan_passage(text)
        quarantined = report.injection_score >= QUARANTINE_THRESHOLD
        decision = "quarantined" if quarantined else ("flagged" if report.injection_score >= WARN_THRESHOLD else "admitted")
        passage = Passage(passage_id=passage_id, source_ref=source_ref, text=report.normalised_text,
                          safety=report.as_dict(), quarantined=quarantined)
        out.append(AdmissionDecision(passage, decision, report.as_dict()))
    return out
