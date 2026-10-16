"""Layer 1: the exact solver, safe parsing, and retrieval provenance."""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.tools import expressions, solver
from app.tools.retrieval import ApprovedKnowledgeBase, Passage


# --------------------------------------------------------------------------- parsing
@pytest.mark.parametrize("text", ["x**2", "3x + 1", "sin(x)*exp(x)", "sqrt(x)/2", "x^3 - 2x", "(x+1)(x-1)"])
def test_parse_accepts_ordinary_maths(text):
    assert expressions.parse(text, "x").expr is not None


@pytest.mark.parametrize("text", [
    "__import__('os')", "x.__class__", "open('/etc/passwd')", "lambda: 1", "x; import os",
    "x**2 + y", "a*x", "(" * 13 + "x" + ")" * 13, "x" * 201, "", "N(x)", "x.subs(x,1)",
])
def test_parse_rejects_unsafe_or_ill_formed(text):
    with pytest.raises(expressions.ExpressionError):
        expressions.parse(text, "x")


def test_parse_rejects_disallowed_functions_when_topic_restricts():
    assert expressions.parse("sin(x)", "x", ["sin"]).expr is not None
    with pytest.raises(expressions.ExpressionError):
        expressions.parse("gamma(x)", "x", ["sin"])


def test_parse_value_accepts_numbers_strings_and_infinity():
    assert expressions.parse_value(4) == 4
    assert expressions.parse_value("4") == 4
    assert expressions.parse_value("2*x", "x") is not None
    assert expressions.parse_value("oo") == expressions.sympy.oo


# --------------------------------------------------------------------------- claims
def _claim(**kw):
    base = {"id": "c1", "var": "x"}
    base.update(kw)
    return base


@pytest.mark.parametrize("claim,expected", [
    (_claim(type="derivative", expression="x**2", claimed="2*x"), "verified"),
    (_claim(type="derivative", expression="x**2", claimed="2x"), "verified"),
    (_claim(type="derivative", expression="x**2", claimed="x"), "mismatch"),
    (_claim(type="derivative", expression="sin(x)", claimed="cos(x)"), "verified"),
    (_claim(type="value_at", expression="x**2", at=3, claimed=9), "verified"),
    (_claim(type="value_at", expression="x**2", at=3, claimed=6), "mismatch"),
    (_claim(type="slope_tangent", expression="t**2", var="t", at_x=2, claimed=4), "verified"),
    (_claim(type="slope_tangent", expression="t**2", var="t", at_x=2, claimed=4.0), "verified"),
    (_claim(type="slope_tangent", expression="t**2", var="t", at_x=2, claimed=2), "mismatch"),
    (_claim(type="slope_secant", expression="t**2", var="t", at_x=2, h=1, claimed=5), "verified"),
    (_claim(type="slope_secant", expression="t**2", var="t", at_x=2, h=0, claimed=5), "mismatch"),
    (_claim(type="limit", expression="sin(x)/x", to=0, claimed=1), "verified"),
    (_claim(type="limit", expression="1/x", to="oo", claimed=0), "verified"),
    (_claim(type="limit", expression="x**2", to="oo", claimed="oo"), "verified"),
    (_claim(type="equivalent", lhs="(x+1)**2", rhs="x**2 + 2*x + 1"), "verified"),
    (_claim(type="equivalent", lhs="(x+1)**2", rhs="x**2 + 1"), "mismatch"),
    (_claim(type="secant_converges", expression="t**2", var="t", at_x=2, h_values=[1, 0.5, 0.1, 0.01]), "verified"),
    (_claim(type="secant_converges", expression="t**2", var="t", at_x=2, h_values=[0.01, 0.1, 1]), "mismatch"),
    (_claim(type="secant_converges", expression="t**2", var="t", at_x=2, h_values=[1, 0]), "mismatch"),
    (_claim(type="derivative", expression="__import__('os')", claimed="0"), "unparseable"),
    (_claim(type="derivative", expression="x**2"), "error"),
    (_claim(type="integral", expression="x**2", claimed="x**3/3"), "unsupported"),
])
def test_solve_claim_statuses(claim, expected):
    result = solver.solve_claim(claim)
    assert result.status == expected, result.detail


def test_secant_converges_reports_tangent_slope_and_secant_slopes():
    r = solver.solve_claim(_claim(type="secant_converges", expression="t**2", var="t", at_x=2, h_values=[1, 0.5, 0.1]))
    assert r.computed == 4 and r.numeric == 4.0
    assert r.extra["secant_slopes"] == [5, 4.5, 4.1]


def test_a_claim_is_never_verified_on_solver_error():
    r = solver.solve_claim(_claim(type="limit", expression="x", to="nonsense", claimed=0))
    assert r.status in {"error", "unparseable", "mismatch"}
    assert not r.ok


def test_solve_claims_keys_by_id():
    out = solver.solve_claims([_claim(id="c1", type="value_at", expression="x", at=1, claimed=1),
                               _claim(id="c2", type="value_at", expression="x", at=1, claimed=2)])
    assert out["c1"].ok and not out["c2"].ok


# --------------------------------------------------------------------------- property tests
coeff = st.integers(min_value=-9, max_value=9)


@settings(max_examples=60, deadline=None)
@given(a=coeff, b=coeff, c=coeff, d=coeff)
def test_true_derivative_of_random_cubic_is_verified(a, b, c, d):
    expr = f"{a}*x**3 + {b}*x**2 + {c}*x + {d}"
    true = f"{3*a}*x**2 + {2*b}*x + {c}"
    assert solver.solve_claim(_claim(type="derivative", expression=expr, claimed=true)).ok


@settings(max_examples=60, deadline=None)
@given(a=coeff, b=coeff, c=coeff, d=coeff, k=st.integers(min_value=1, max_value=5))
def test_perturbed_derivative_of_random_cubic_is_rejected(a, b, c, d, k):
    expr = f"{a}*x**3 + {b}*x**2 + {c}*x + {d}"
    wrong = f"{3*a}*x**2 + {2*b}*x + {c + k}"
    assert not solver.solve_claim(_claim(type="derivative", expression=expr, claimed=wrong)).ok


@settings(max_examples=60, deadline=None)
@given(a=st.floats(min_value=-5, max_value=5, allow_nan=False), h=st.floats(min_value=0.01, max_value=2, allow_nan=False))
def test_secant_slope_of_square_matches_identity(a, h):
    # ((a+h)^2 - a^2)/h = 2a + h exactly.
    r = solver.solve_claim(_claim(type="slope_secant", expression="x**2", at_x=a, h=h, claimed=2 * a + h, tolerance=1e-7))
    assert r.ok, r.detail


# --------------------------------------------------------------------------- retrieval
def test_retrieval_respects_quarantine_and_allowed_sources():
    kb = ApprovedKnowledgeBase()
    kb.add(Passage("p1", "src:a", "The derivative is the limit of secant slopes as h tends to zero."))
    kb.add(Passage("p2", "src:b", "Secant slopes approach the tangent slope.", quarantined=True))
    kb.add(Passage("p3", "src:c", "Secant slopes approach the tangent slope."))
    hits = kb.retrieve("secant slope tangent", allowed_source_refs=["src:a", "src:b"])
    assert [p.passage_id for p in hits] == ["p1"], "quarantined and non-approved sources never come back"
    assert all(p.as_context()["role"] == "source_data" for p in hits)
    assert kb.source_refs() == ["src:a", "src:c"]


def test_retrieval_rejects_duplicate_ids():
    kb = ApprovedKnowledgeBase()
    kb.add(Passage("p1", "src:a", "text"))
    with pytest.raises(ValueError):
        kb.add(Passage("p1", "src:a", "text"))
