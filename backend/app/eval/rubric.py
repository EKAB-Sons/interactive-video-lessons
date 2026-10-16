"""Written review rubric and inter-reviewer agreement.

Three requirements; each is a yes/no judgement by a
reviewer looking at the request, the scene and the final response. A response
passes the rubric only when all three are yes. Two reviewers label independently
and we report percent agreement and Cohen's kappa per criterion and overall, so
high agreement can be distinguished from agreement expected by chance.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any, Hashable, Iterable, Sequence

RUBRIC = {
    "question_identified": "The response addresses the question the student actually asked (paraphrases and follow-ups included).",
    "object_identified": "The response is about the object the student selected or clearly referred to.",
    "mathematically_sound": "Every stated value, slope or limit is correct and the explanation does not mislead.",
}


def rubric_pass(label: dict[str, Any]) -> bool:
    return all(bool(label.get(k)) for k in RUBRIC)


def percent_agreement(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("label sequences must be non-empty and aligned")
    return sum(x == y for x, y in zip(a, b)) / len(a)


def cohens_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Returns 1.0 when both reviewers agree on a single
    category throughout (p_e == 1), which the textbook formula leaves undefined."""
    if len(a) != len(b) or not a:
        raise ValueError("label sequences must be non-empty and aligned")
    n = len(a)
    p_o = percent_agreement(a, b)
    ca, cb = Counter(a), Counter(b)
    p_e = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def _align(labels: Iterable[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """reviewer_id -> case_id -> label"""
    by_reviewer: dict[str, dict[str, dict[str, Any]]] = {}
    for lab in labels:
        by_reviewer.setdefault(lab["reviewer_id"], {})[lab["case_id"]] = lab
    return by_reviewer


def rubric_report(labels: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """labels: [{case_id, reviewer_id, question_identified, object_identified, mathematically_sound}]"""
    by_reviewer = _align(labels)
    reviewers = sorted(by_reviewer)
    if len(reviewers) < 2:
        raise ValueError("agreement needs at least two reviewers")
    common = sorted(set.intersection(*(set(by_reviewer[r]) for r in reviewers)))
    pairs = {}
    for r1, r2 in combinations(reviewers, 2):
        per_criterion = {}
        for crit in list(RUBRIC) + ["overall"]:
            key = (lambda l: rubric_pass(l)) if crit == "overall" else (lambda l, c=crit: bool(l.get(c)))
            a = [key(by_reviewer[r1][c]) for c in common]
            b = [key(by_reviewer[r2][c]) for c in common]
            per_criterion[crit] = {"percent_agreement": round(percent_agreement(a, b), 4), "kappa": round(cohens_kappa(a, b), 4)}
        pairs[f"{r1} vs {r2}"] = per_criterion
    # Consensus pass: every reviewer marks all three criteria yes.
    consensus = {c: all(rubric_pass(by_reviewer[r][c]) for r in reviewers) for c in common}
    disagreements = [c for c in common if len({rubric_pass(by_reviewer[r][c]) for r in reviewers}) > 1]
    return {"reviewers": reviewers, "cases_labelled_by_all": len(common), "agreement": pairs,
            "consensus_pass_count": sum(consensus.values()), "disagreements": disagreements}
