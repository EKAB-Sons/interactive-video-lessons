"""Check layer 3: grounding and narration discipline.

* Source references must be a subset of the lesson's approved sources. A
  planner cannot widen the trust set by citing something new.
* Narration may only state a number through a {{claim:cN}} placeholder. Any
  other numeral is a value we cannot recompute and therefore cannot show.
  Scene constants (an object's at_x, domain endpoints) are allowed because the
  scene itself is trusted state.
* Narration must not carry instruction-like or role markers: evidence that an
  injected instruction reached the output (see app.safety).
"""
from __future__ import annotations

import re
from typing import Any

from .issues import Issue, Severity

LAYER = "grounding"
PLACEHOLDER = re.compile(r"\{\{claim:(c[0-9]{1,3})\}\}")
_NUMBER = re.compile(r"(?<![a-zA-Z_{])[-+]?\d+(?:\.\d+)?")
_MARKERS = re.compile(r"(?i)(ignore (all |the )?(previous|prior|above) instructions|system prompt|you are now|as an ai|BEGIN SYSTEM|<\|im_start\|>|\[INST\])")


def check_sources(proposal_refs: list[str], approved: list[str], path: str = "/source_refs") -> list[Issue]:
    return [Issue("unsupported_source_reference", f"{ref!r} is not an approved source for this lesson", f"{path}/{i}",
                  repairable=True, layer=LAYER)
            for i, ref in enumerate(proposal_refs) if ref not in approved]


def scene_constants(scene_objects: dict[str, Any]) -> set[str]:
    consts: set[str] = set()
    for obj in scene_objects.values():
        for key in ("at_x", "h"):
            if key in obj and isinstance(obj[key], (int, float)):
                consts.add(_fmt(obj[key]))
        for v in obj.get("domain", []) or []:
            consts.add(_fmt(v))
    return consts


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def check_narration_text(text: str, claims_by_id: dict[str, dict[str, Any]], allowed_constants: set[str],
                         path: str) -> list[Issue]:
    issues: list[Issue] = []
    for m in PLACEHOLDER.finditer(text):
        if m.group(1) not in claims_by_id:
            issues.append(Issue("unknown_claim_placeholder", f"narration cites claim {m.group(1)} which is not declared", path, layer=LAYER))
    stripped = PLACEHOLDER.sub(" ", text)
    for m in _NUMBER.finditer(stripped):
        token = m.group(0).lstrip("+")
        if token.lstrip("-") in allowed_constants or token in allowed_constants:
            continue
        issues.append(Issue("unverified_numeral_in_text",
                            f"text states the value {token!r} without a verified claim placeholder", path, layer=LAYER))
        break
    if _MARKERS.search(text):
        issues.append(Issue("instruction_marker_in_output", "text contains an instruction/role marker; possible injected instruction reaching output",
                            path, repairable=False, layer=LAYER))
    return issues


def check_narrations(operations: list[dict[str, Any]], claims_by_id: dict[str, dict[str, Any]],
                     scene_objects: dict[str, Any], base_path: str = "/operations") -> list[Issue]:
    consts = scene_constants(scene_objects)
    issues: list[Issue] = []
    for i, op in enumerate(operations):
        if op.get("type") == "set_narration" and isinstance(op.get("text"), str):
            issues.extend(check_narration_text(op["text"], claims_by_id, consts, f"{base_path}/{i}/text"))
        if op.get("type") == "annotate_value" and isinstance(op.get("label_text"), str):
            issues.extend(check_narration_text(op["label_text"], claims_by_id, consts, f"{base_path}/{i}/label_text"))
    return issues
