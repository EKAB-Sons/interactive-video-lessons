"""Check layer 2: operations against the DSL registry and the simulated scene.

For every operation, in order:
  * the type exists in the registry and is allowed for the topic,
  * required arguments are present with the declared types,
  * object references name objects that exist *at that step* with the right kind,
  * created ids are well-formed and not already taken,
  * only branch-created objects may be removed,
  * fact-bearing operations name a claim of a permitted type,
  * free-text labels carry no numerals (a value must come via annotate_value).
The operation is applied to the simulator only if it passed, so later checks
see a consistent scene.
"""
from __future__ import annotations

import re
from typing import Any

from .. import contracts
from ..tools import expressions
from .issues import Issue, Severity
from .scene_sim import OBJECT_ID, SceneSimulator

LAYER = "operations"
_NUMERAL = re.compile(r"[0-9=]")
_CLAIM_REF = re.compile(r"^c[0-9]{1,3}$")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _arg_type_ok(aspec: dict[str, Any], value: Any) -> str | None:
    t = aspec["type"]
    if t in ("object_ref", "new_object_id", "variable", "expression", "claim_ref", "string"):
        if not isinstance(value, str) or not value:
            return f"must be a non-empty string"
        if t == "string" and len(value) > aspec.get("max_length", 10_000):
            return f"longer than {aspec['max_length']} characters"
        if t == "variable" and not re.fullmatch(r"[a-zA-Z]", value):
            return "must be a single-letter variable"
        if t == "new_object_id" and not OBJECT_ID.match(value):
            return "must look like namespace.name (lowercase)"
        if t == "claim_ref" and not _CLAIM_REF.match(value):
            return "must look like c1"
        return None
    if t == "number":
        return None if _is_number(value) else "must be a number"
    if t == "number_array":
        if not isinstance(value, list) or not all(_is_number(v) for v in value):
            return "must be an array of numbers"
        if not aspec.get("min_items", 0) <= len(value) <= aspec.get("max_items", 10_000):
            return f"must have between {aspec.get('min_items', 0)} and {aspec.get('max_items')} items"
        return None
    return f"unknown argument type {t}"


def check_operations(
    operations: list[dict[str, Any]],
    sim: SceneSimulator,
    claims_by_id: dict[str, dict[str, Any]],
    topic: str,
    base_path: str = "/operations",
) -> tuple[list[Issue], list[int]]:
    """Returns (issues, indices of operations that passed every check)."""
    issues: list[Issue] = []
    passed: list[int] = []
    tspec = contracts.topic_spec(topic) or {"allowed_operations": [], "allowed_functions": None}
    allowed_ops = set(tspec["allowed_operations"])
    for i, op in enumerate(operations):
        path = f"{base_path}/{i}"
        op_type = op.get("type")
        spec = contracts.operation_spec(op_type or "")
        if spec is None:
            issues.append(Issue("operation_not_in_registry", f"operation {op_type!r} is not a supported scene operation", path, layer=LAYER))
            continue
        if op_type not in allowed_ops:
            issues.append(Issue("operation_not_allowed_for_topic", f"operation {op_type!r} is not permitted for topic {topic!r}", path, layer=LAYER))
            continue
        ok = True
        for arg in spec["required"]:
            if arg not in op:
                issues.append(Issue("missing_argument", f"{op_type} requires {arg!r}", f"{path}/{arg}", layer=LAYER))
                ok = False
        for arg, value in op.items():
            if arg == "type":
                continue
            aspec = spec["args"].get(arg)
            if aspec is None:
                issues.append(Issue("unknown_argument", f"{op_type} does not take {arg!r}", f"{path}/{arg}", layer=LAYER))
                ok = False
                continue
            problem = _arg_type_ok(aspec, value)
            if problem:
                issues.append(Issue("argument_type", f"{op_type}.{arg} {problem}", f"{path}/{arg}", layer=LAYER))
                ok = False
        if not ok:
            continue
        # References must exist now, with the right kind.
        for arg, kinds in spec["refs"].items():
            ref = op[arg]
            if not sim.exists(ref):
                issues.append(Issue("unknown_object", f"{op_type}.{arg} names {ref!r}, which is not in the scene at this step", f"{path}/{arg}", layer=LAYER))
                ok = False
            elif kinds and sim.kind(ref) not in kinds:
                issues.append(Issue("wrong_object_kind", f"{op_type}.{arg} must be a {'/'.join(kinds)}, got {sim.kind(ref)}", f"{path}/{arg}", layer=LAYER))
                ok = False
        if "creates" in spec:
            new_id = op[spec["creates"]]
            if sim.exists(new_id):
                issues.append(Issue("object_id_taken", f"{new_id!r} already exists", f"{path}/{spec['creates']}", layer=LAYER))
                ok = False
        if "removes" in spec and sim.exists(op[spec["removes"]]) and sim.origin(op[spec["removes"]]) != "branch":
            issues.append(Issue("protected_object", f"{op[spec['removes']]!r} belongs to the base lesson and may not be removed", f"{path}/{spec['removes']}", layer=LAYER))
            ok = False
        if spec["fact_bearing"]:
            cref = op.get("claim_ref")
            claim = claims_by_id.get(cref)
            permitted = spec["args"]["claim_ref"]["claim_types"]
            if claim is None:
                issues.append(Issue("unknown_claim_ref", f"{op_type} references claim {cref!r}, which the proposal does not declare", f"{path}/claim_ref", layer=LAYER))
                ok = False
            elif claim.get("type") not in permitted:
                issues.append(Issue("claim_type_mismatch", f"{op_type} needs a {'/'.join(permitted)} claim, got {claim.get('type')}", f"{path}/claim_ref", layer=LAYER))
                ok = False
            else:
                ok = _fact_bearing_consistent(op, spec, claim, sim, path, issues) and ok
        if op_type == "add_label" and _NUMERAL.search(op["text"]):
            issues.append(Issue("numeral_in_free_label", "a label that states a value must be an annotate_value with a claim_ref", f"{path}/text", layer=LAYER))
            ok = False
        if op_type == "plot_function":
            try:
                expressions.parse(op["expression"], op["var"], tspec.get("allowed_functions"))
            except expressions.ExpressionError as exc:
                issues.append(Issue("unparseable_expression", str(exc), f"{path}/expression", layer=LAYER))
                ok = False
            lo, hi = op["domain"]
            if not lo < hi:
                issues.append(Issue("bad_domain", "domain must be [lo, hi] with lo < hi", f"{path}/domain", layer=LAYER))
                ok = False
        if ok:
            sim.apply(op)
            passed.append(i)
    return issues, passed


def _fact_bearing_consistent(op: dict[str, Any], spec: dict[str, Any], claim: dict[str, Any],
                             sim: SceneSimulator, path: str, issues: list[Issue]) -> bool:
    """The operation's own arguments must agree with the claim it cites, and
    the claim must be about the curve the operation draws on. Otherwise a
    planner could verify a true claim about one curve and draw it on another."""
    ok = True
    curve_id = op.get("curve")
    anchor_at: dict[str, Any] = {}
    if not curve_id and op.get("anchor") and sim.exists(op["anchor"]):
        anchor = sim.objects[op["anchor"]]
        if anchor.get("kind") == "curve":
            curve_id = op["anchor"]
        elif anchor.get("kind") == "line":
            curve_id = anchor.get("curve")
            anchor_at = {k: anchor[k] for k in ("at_x", "h") if k in anchor}
    if curve_id and sim.exists(curve_id):
        curve = sim.objects[curve_id]
        if curve.get("expression") and claim.get("expression") and not expressions_equivalent(curve, claim):
            issues.append(Issue("claim_curve_mismatch", f"claim {claim['id']} is about {claim.get('expression')!r} but {curve_id} plots {curve.get('expression')!r}", f"{path}/claim_ref", layer=LAYER))
            ok = False
    for arg in ("at_x", "h"):
        given = op.get(arg, anchor_at.get(arg))
        if given is not None and arg in claim and float(given) != float(claim[arg]):
            issues.append(Issue("claim_argument_mismatch", f"{op['type']}.{arg}={given} but claim {claim['id']} has {arg}={claim[arg]}", f"{path}/{arg}", layer=LAYER))
            ok = False
    if "h_values" in op and "h_values" in claim and [float(h) for h in op["h_values"]] != [float(h) for h in claim["h_values"]]:
        issues.append(Issue("claim_argument_mismatch", f"h_values differ from claim {claim['id']}", f"{path}/h_values", layer=LAYER))
        ok = False
    if op["type"] == "annotate_value" and f"{{{{claim:{claim['id']}}}}}" not in op["label_text"]:
        issues.append(Issue("label_missing_placeholder", "annotate_value.label_text must contain the {{claim:ID}} placeholder of its claim_ref", f"{path}/label_text", layer=LAYER))
        ok = False
    return ok


def expressions_equivalent(curve: dict[str, Any], claim: dict[str, Any]) -> bool:
    from ..tools.solver import expressions_equivalent as eq
    var = claim.get("var", "x")
    if curve.get("var", var) != var:
        return False
    return eq(curve["expression"], claim["expression"], var)
