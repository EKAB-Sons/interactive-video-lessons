"""Safe parsing of mathematical expressions supplied by a planner.

A planner's `expression` string is untrusted input. We therefore:
  * reject anything outside a small character whitelist before SymPy sees it,
  * parse with a fixed local namespace (no attribute access, no builtins),
  * bound length and nesting so a pathological string cannot stall the solver,
  * and never call eval() on the raw text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

MAX_EXPRESSION_LENGTH = 200
MAX_PAREN_DEPTH = 12
_ALLOWED_CHARS = re.compile(r"^[0-9a-zA-Z_+\-*/^(). ,]*$")
_FORBIDDEN_TOKENS = re.compile(r"(__|\.\.|lambda|import|exec|eval|open|getattr|setattr|subs|func|\bN\b)")

ALLOWED_FUNCTIONS: dict[str, object] = {
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "exp": sympy.exp,
    "log": sympy.log,
    "ln": sympy.log,
    "sqrt": sympy.sqrt,
    "Abs": sympy.Abs,
    "abs": sympy.Abs,
    "pi": sympy.pi,
    "E": sympy.E,
}

_TRANSFORMATIONS = standard_transformations + (convert_xor, implicit_multiplication_application)

# parse_expr normally does `from sympy import *` into its global namespace,
# which would let an expression reach any SymPy name (gamma, Integral, ...).
# We give it only the constructors the tokenizer transformations themselves emit.
_GLOBALS: dict[str, object] = {
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    "Rational": sympy.Rational,
    "Symbol": sympy.Symbol,
    "Function": sympy.Function,
}
_FUNCTION_NAMES = {"sin": "sin", "cos": "cos", "tan": "tan", "exp": "exp", "log": "log", "Abs": "Abs"}


class ExpressionError(ValueError):
    """Raised when an expression is unsafe or unparseable. The message is
    safe to surface in a verification issue."""


@dataclass(frozen=True)
class Parsed:
    expr: sympy.Expr
    var: sympy.Symbol
    text: str


def _check_text(text: str) -> None:
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("expression is empty")
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(f"expression longer than {MAX_EXPRESSION_LENGTH} characters")
    if not _ALLOWED_CHARS.match(text):
        raise ExpressionError("expression contains characters outside the allowed set")
    if _FORBIDDEN_TOKENS.search(text):
        raise ExpressionError("expression contains a forbidden token")
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            if depth > MAX_PAREN_DEPTH:
                raise ExpressionError("expression nesting too deep")
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise ExpressionError("unbalanced parentheses")
    if depth != 0:
        raise ExpressionError("unbalanced parentheses")


def parse(text: str, var: str = "x", allowed_functions: list[str] | None = None) -> Parsed:
    """Parse `text` as an expression in the single variable `var`.

    Any other free symbol is an error: a claim about f(x) that secretly depends
    on an unnamed `a` cannot be recomputed and is therefore not a claim.
    """
    _check_text(text)
    if not re.fullmatch(r"[a-zA-Z]", var or ""):
        raise ExpressionError("variable must be a single letter")
    symbol = sympy.Symbol(var, real=True)
    local = {name: fn for name, fn in ALLOWED_FUNCTIONS.items()
             if allowed_functions is None or name in allowed_functions or name in ("pi", "E")}
    local[var] = symbol
    try:
        expr = parse_expr(text, local_dict=local, global_dict=dict(_GLOBALS),
                          transformations=_TRANSFORMATIONS, evaluate=True)
    except Exception as exc:  # SymPy raises many distinct types; all mean "not an expression".
        raise ExpressionError(f"could not parse expression: {type(exc).__name__}") from exc
    if not isinstance(expr, sympy.Expr):
        raise ExpressionError("input is not a mathematical expression")
    extra = {str(s) for s in expr.free_symbols} - {var}
    if extra:
        raise ExpressionError(f"unexpected free symbols: {sorted(extra)}")
    if expr.atoms(sympy.core.function.AppliedUndef):
        raise ExpressionError("unknown function name")
    permitted = {_FUNCTION_NAMES[n] for n in local if n in _FUNCTION_NAMES}
    used = {type(f).__name__ for f in expr.atoms(sympy.Function)}
    if used - permitted:
        raise ExpressionError(f"function not permitted for this topic: {sorted(used - permitted)}")
    return Parsed(expr=expr, var=symbol, text=text)


def parse_value(value: str | int | float, var: str = "x") -> sympy.Expr:
    """Parse a claimed result. Numbers pass through; strings are parsed like
    expressions (so '2*x' or '4' or 'oo' are all acceptable claimed values)."""
    if isinstance(value, bool):
        raise ExpressionError("claimed value must be a number or expression")
    if isinstance(value, (int, float)):
        return sympy.nsimplify(value) if float(value).is_integer() else sympy.Float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("oo", "inf", "infinity"):
            return sympy.oo
        if stripped in ("-oo", "-inf", "-infinity"):
            return -sympy.oo
        return parse(stripped, var).expr
    raise ExpressionError("claimed value must be a number or expression")
