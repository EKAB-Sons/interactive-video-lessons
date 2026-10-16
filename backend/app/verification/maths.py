"""Check layer 4: mathematical correctness.

Every declared claim is recomputed by the exact solver. A claim that is not
verified blocks every operation and every narration placeholder that depends
on it. Verified values are then substituted into narration and labels, so the
text the student sees was produced by the solver, not by the planner.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from .. import contracts
from ..tools import solver
from .grounding import PLACEHOLDER
from .issues import Issue

LAYER = "maths"


def check_claims(claims: list[dict[str, Any]], topic: str, base_path: str = "/claims") -> tuple[list[Issue], dict[str, solver.ClaimResult]]:
    issues: list[Issue] = []
    tspec = contracts.topic_spec(topic) or {}
    allowed_types = set(tspec.get("allowed_claim_types", []))
    allowed_functions = tspec.get("allowed_functions")
    seen: set[str] = set()
    results: dict[str, solver.ClaimResult] = {}
    for i, claim in enumerate(claims):
        path = f"{base_path}/{i}"
        cid = str(claim.get("id"))
        if cid in seen:
            issues.append(Issue("duplicate_claim_id", f"claim id {cid} declared twice", f"{path}/id", layer=LAYER))
            continue
        seen.add(cid)
        schema_errors = contracts.validation_errors("claim", claim)
        if schema_errors:
            issues.append(Issue("claim_schema_violation", schema_errors[0]["message"], f"{path}{schema_errors[0]['path']}", layer=LAYER))
            results[cid] = solver.ClaimResult(cid, str(claim.get("type")), "error", detail="schema violation")
            continue
        if claim["type"] not in allowed_types:
            issues.append(Issue("claim_type_not_allowed_for_topic", f"claim type {claim['type']!r} not permitted for topic {topic!r}", f"{path}/type", layer=LAYER))
            results[cid] = solver.ClaimResult(cid, claim["type"], "unsupported")
            continue
        result = solver.solve_claim(claim, allowed_functions)
        results[cid] = result
        if not result.ok:
            code = {"mismatch": "claim_incorrect", "unparseable": "claim_unparseable",
                    "unsupported": "claim_unsupported", "error": "claim_error"}[result.status]
            issues.append(Issue(code, f"claim {cid} ({claim['type']}): {result.detail or result.status}", path,
                                layer=LAYER, computed=result.computed))
    return issues, results


def _render_value(result: solver.ClaimResult) -> str:
    v = result.computed
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:.6g}"
    return str(v)


def substitute_verified_values(operations: list[dict[str, Any]], results: dict[str, solver.ClaimResult]) -> list[dict[str, Any]]:
    """Return a deep copy of the operations with every {{claim:cN}} replaced by
    the solver's value. Call only after all referenced claims are verified."""
    out = copy.deepcopy(operations)

    def sub(text: str) -> str:
        def repl(m: re.Match[str]) -> str:
            r = results.get(m.group(1))
            if r is None or not r.ok:
                raise ValueError(f"placeholder {m.group(0)} refers to an unverified claim")
            return _render_value(r)
        return PLACEHOLDER.sub(repl, text)

    for op in out:
        if op.get("type") == "set_narration":
            op["text"] = sub(op["text"])
        if op.get("type") == "annotate_value":
            op["label_text"] = sub(op["label_text"])
            r = results[op["claim_ref"]]
            op["value"] = r.computed
        if op.get("type") in ("draw_tangent", "draw_secant"):
            op["slope"] = results[op["claim_ref"]].computed
        if op.get("type") == "show_secant_sequence":
            r = results[op["claim_ref"]]
            op["tangent_slope"] = r.computed
            op["secant_slopes"] = r.extra.get("secant_slopes", [])
    return out
