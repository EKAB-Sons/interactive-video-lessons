"""Exact solver for the claim types the derivatives topic permits.

Each claim type has exactly one recompute function. The verifier never trusts
`claimed`; it recomputes and compares. Comparison is symbolic first
(simplify(computed - claimed) == 0) and numeric second (within tolerance), so a
planner that writes 2*x where we compute 2x, or 4.0 where we compute 4, is not
penalised for notation, while a wrong value is always caught.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sympy

from .expressions import ExpressionError, parse, parse_value

SOLVER_VERSION = "solver-v1"
DEFAULT_TOLERANCE = 1e-9
SUPPORTED_CLAIM_TYPES = (
    "derivative", "value_at", "slope_tangent", "slope_secant", "limit", "equivalent", "secant_converges",
)


@dataclass
class ClaimResult:
    id: str
    type: str
    status: str                     # verified | mismatch | unparseable | unsupported | error
    claimed: Any = None
    computed: Any = None
    detail: str = ""
    numeric: float | None = None    # a float of `computed` when it is a number (used for narration substitution)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "verified"

    def as_dict(self) -> dict[str, Any]:
        out = {"id": self.id, "type": self.type, "status": self.status, "claimed": self.claimed,
               "computed": self.computed, "detail": self.detail, "solver_version": SOLVER_VERSION}
        out.update(self.extra)
        return out


def _num(x: sympy.Expr) -> float | None:
    try:
        if x.is_number and x.is_finite is not False:
            return float(x)
    except (TypeError, ValueError):
        return None
    return None


def _format(x: sympy.Expr) -> str | float | int:
    """A JSON-friendly rendering: ints as ints, rationals/floats as floats, else a string."""
    if x.is_Integer:
        return int(x)
    n = _num(x)
    if n is not None and x.is_number:
        return n if x != sympy.oo and x != -sympy.oo else str(x)
    return str(x)


def _agree(computed: sympy.Expr, claimed: sympy.Expr, tol: float) -> bool:
    if computed == claimed:
        return True
    if computed in (sympy.oo, -sympy.oo) or claimed in (sympy.oo, -sympy.oo):
        return computed == claimed
    try:
        if sympy.simplify(computed - claimed) == 0:
            return True
    except Exception:
        pass
    a, b = _num(computed), _num(claimed)
    if a is not None and b is not None:
        return abs(a - b) <= max(tol, tol * abs(a))
    # Last resort for expressions with a free variable: compare at a few points.
    syms = list((computed.free_symbols | claimed.free_symbols))
    if len(syms) == 1:
        s = syms[0]
        try:
            return all(abs(float((computed - claimed).subs(s, v))) <= tol for v in (0.37, 1.0, 2.5, -1.3))
        except Exception:
            return False
    return False


def _secant_slope(expr: sympy.Expr, var: sympy.Symbol, a: float, h: float) -> sympy.Expr:
    a_, h_ = sympy.nsimplify(a), sympy.nsimplify(h)
    return sympy.simplify((expr.subs(var, a_ + h_) - expr.subs(var, a_)) / h_)


def solve_claim(claim: dict[str, Any], allowed_functions: list[str] | None = None) -> ClaimResult:
    cid = str(claim.get("id", "?"))
    ctype = claim.get("type")
    tol = float(claim.get("tolerance", DEFAULT_TOLERANCE))
    var_name = claim.get("var", "x")
    if ctype not in SUPPORTED_CLAIM_TYPES:
        return ClaimResult(cid, str(ctype), "unsupported", detail="no exact check for this claim type")
    try:
        if ctype == "equivalent":
            lhs = parse(claim["lhs"], var_name, allowed_functions).expr
            rhs = parse(claim["rhs"], var_name, allowed_functions).expr
            same = _agree(lhs, rhs, tol)
            return ClaimResult(cid, ctype, "verified" if same else "mismatch",
                               claimed=claim["rhs"], computed=str(sympy.simplify(lhs)),
                               detail="" if same else "lhs and rhs are not equivalent")

        parsed = parse(claim["expression"], var_name, allowed_functions)
        expr, var = parsed.expr, parsed.var

        if ctype == "secant_converges":
            a = float(claim["at_x"])
            hs = [float(h) for h in claim["h_values"]]
            if len(hs) < 2 or any(h == 0 for h in hs):
                return ClaimResult(cid, ctype, "mismatch", detail="h_values must be non-zero and at least two")
            if not all(abs(hs[i + 1]) < abs(hs[i]) for i in range(len(hs) - 1)):
                return ClaimResult(cid, ctype, "mismatch", detail="h_values must strictly decrease in magnitude")
            tangent = sympy.diff(expr, var).subs(var, sympy.nsimplify(a))
            slopes = [_secant_slope(expr, var, a, h) for h in hs]
            gaps = [abs(float(s - tangent)) for s in slopes]
            converging = all(gaps[i + 1] <= gaps[i] + tol for i in range(len(gaps) - 1)) and gaps[-1] <= max(1e-6, 10 * abs(hs[-1]) * (1 + abs(float(tangent))))
            return ClaimResult(cid, ctype, "verified" if converging else "mismatch",
                               computed=_format(tangent), numeric=_num(tangent),
                               detail="" if converging else "secant slopes do not approach the tangent slope",
                               extra={"secant_slopes": [_format(s) for s in slopes]})

        if ctype == "derivative":
            computed = sympy.simplify(sympy.diff(expr, var))
        elif ctype == "value_at":
            computed = sympy.simplify(expr.subs(var, sympy.nsimplify(claim["at"])))
        elif ctype == "slope_tangent":
            computed = sympy.simplify(sympy.diff(expr, var).subs(var, sympy.nsimplify(claim["at_x"])))
        elif ctype == "slope_secant":
            if float(claim["h"]) == 0:
                return ClaimResult(cid, ctype, "mismatch", detail="h must be non-zero")
            computed = _secant_slope(expr, var, float(claim["at_x"]), float(claim["h"]))
        elif ctype == "limit":
            to = claim["to"]
            target = sympy.oo if to in ("oo", "inf") else (-sympy.oo if to in ("-oo", "-inf") else sympy.nsimplify(to))
            computed = sympy.limit(expr, var, target)
        else:  # pragma: no cover - guarded by SUPPORTED_CLAIM_TYPES
            return ClaimResult(cid, ctype, "unsupported")

        claimed = parse_value(claim["claimed"], var_name)
        ok = _agree(computed, claimed, tol)
        return ClaimResult(cid, ctype, "verified" if ok else "mismatch",
                           claimed=claim["claimed"], computed=_format(computed), numeric=_num(computed),
                           detail="" if ok else f"claimed {claim['claimed']!r} but computed {computed}")
    except ExpressionError as exc:
        return ClaimResult(cid, str(ctype), "unparseable", detail=str(exc))
    except KeyError as exc:
        return ClaimResult(cid, str(ctype), "error", detail=f"missing field {exc.args[0]!r}")
    except Exception as exc:  # Any solver failure is reported, never swallowed, and never counts as verified.
        return ClaimResult(cid, str(ctype), "error", detail=f"solver error: {type(exc).__name__}")


def solve_claims(claims: list[dict[str, Any]], allowed_functions: list[str] | None = None) -> dict[str, ClaimResult]:
    return {str(c.get("id")): solve_claim(c, allowed_functions) for c in claims}


def expressions_equivalent(a: str, b: str, var: str = "x") -> bool:
    try:
        return _agree(parse(a, var).expr, parse(b, var).expr, DEFAULT_TOLERANCE)
    except ExpressionError:
        return False
