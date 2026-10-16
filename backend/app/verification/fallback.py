"""Checked fallbacks when a plan cannot be accepted.

When we decline or degrade, the student still gets something true and a
concrete next step. The only facts a fallback may state are solver-verified
values from the proposal's own claims; if there are none, we do not invent a
sentence, we offer waiting, retrying or returning to the lesson. A loading
message does not count as a useful response.
"""
from __future__ import annotations

from typing import Any

from ..tools.solver import ClaimResult

_TEMPLATES = {
    "slope_tangent": "The slope of the tangent to {expr} at {var} = {at} is {value}.",
    "slope_secant": "The slope of the secant to {expr} between {var} = {at} and {var} = {at} + {h} is {value}.",
    "derivative": "The derivative of {expr} with respect to {var} is {value}.",
    "value_at": "The value of {expr} at {var} = {at} is {value}.",
    "limit": "The limit of {expr} as {var} tends to {to} is {value}.",
    "secant_converges": "As h shrinks, the secant slopes of {expr} at {var} = {at} approach {value}, the tangent slope.",
}

_NEXT_STEP = {
    "deadline": "We could not produce a checked visual answer within the time budget. You can wait, retry, or return to the lesson.",
    "revision_failed": "We could not verify a visual explanation for this question. You can rephrase, select the object again, or return to the lesson.",
    "cannot_answer": "The lesson cannot answer this reliably from the approved material. You can rephrase or return to the lesson.",
    "out_of_scope": "This question is outside what this lesson can reliably show. You can return to the lesson or ask about the current scene.",
    "provider_error": "The planning service is unavailable. You can wait, retry, or return to the lesson.",
    "timeout": "The planning service did not respond in time. You can wait, retry, or return to the lesson.",
}


def _fmt(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def build_fallback(claim_results: dict[str, ClaimResult], context: dict[str, Any], *, reason: str,
                   claims_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    verified = [r for r in claim_results.values() if r.ok and r.computed is not None]
    sentences: list[str] = []
    for r in verified:
        claim = (claims_by_id or {}).get(r.id, {})
        tpl = _TEMPLATES.get(r.type)
        if tpl and claim:
            sentences.append(tpl.format(expr=claim.get("expression", "the function"), var=claim.get("var", "x"),
                                        at=_fmt(claim.get("at_x", claim.get("at", ""))), h=_fmt(claim.get("h", "")),
                                        to=claim.get("to", ""), value=_fmt(r.computed)))
    if sentences:
        return {"kind": "checked_text", "text": " ".join(sentences) + " " + _NEXT_STEP.get(reason, _NEXT_STEP["revision_failed"]),
                "verified_claim_ids": [r.id for r in verified]}
    return {"kind": "offer_wait_retry_return", "text": _NEXT_STEP.get(reason, _NEXT_STEP["revision_failed"]), "verified_claim_ids": []}
