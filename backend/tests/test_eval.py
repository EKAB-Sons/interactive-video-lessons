"""Evaluation harness scoring rules and fault coverage."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.eval import FAULTS, cohens_kappa, learning_report, load_cases, percent_agreement, rubric_report, run_faults, run_heldout
from app.eval.heldout import Case, check_leakage
from tests.fixtures import SOURCE, context_packet_fixture, proposal_fixture, scene_fixture

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "eval"


def _case(cid, attempts, *, in_scope=True, group=None, question="Why is this the speed?"):
    return Case(cid, group or cid, in_scope, context_packet_fixture(question_text=question), scene_fixture(), attempts)


def _clarification():
    return {"kind": "clarification", "request_id": "request-demo-001", "status": "needs_clarification",
            "question": "Which object?", "candidate_object_ids": ["graph.tangent", "graph.curve"]}


# --------------------------------------------------------------------------- held-out rule
def test_in_scope_success_requires_accepted_and_withholding_counts_as_failure():
    wrong = proposal_fixture(); wrong["claims"][0]["claimed"] = 5
    rep = run_heldout([
        _case("ok", [proposal_fixture()]),
        _case("repaired", [wrong, proposal_fixture()]),
        _case("clarified", [_clarification()]),
        _case("timed-out", ["timeout"]),
        _case("twice-wrong", [wrong, wrong]),
    ])
    by = {o.case_id: o for o in rep.outcomes}
    assert by["ok"].success and by["repaired"].success and by["repaired"].attempts == 2
    assert not by["clarified"].success and by["clarified"].final_status == "needs_clarification"
    assert not by["timed-out"].success and not by["twice-wrong"].success
    assert rep.passed == 2 and rep.pass_rate == pytest.approx(0.4)
    assert rep.as_dict()["enough_cases_for_claim"] is False and rep.meets_target() is False


def test_out_of_scope_success_means_withheld_and_stays_out_of_denominator():
    oos = proposal_fixture(); oos["claims"].append({"id": "c9", "type": "integral", "expression": "t**2", "var": "t", "claimed": "t**3/3"})
    rep = run_heldout([_case("oos-withheld", [oos, oos], in_scope=False), _case("oos-answered", [proposal_fixture()], in_scope=False)])
    assert [o.success for o in rep.out_of_scope] == [True, False]
    assert rep.in_scope == [] and rep.pass_rate == 0.0


def test_meets_target_needs_100_cases_90_passes_and_no_leakage():
    rep = run_heldout([_case(f"c{i}", [proposal_fixture()], question=f"Why is this the speed? (variant {i})") for i in range(100)])
    assert rep.meets_target() is True
    rep.leakage.append("planted")
    assert rep.meets_target() is False


def test_leakage_guard_catches_shared_groups_and_exact_duplicates():
    held = [_case("h1", [], group="fam-a"), _case("h2", [], group="fam-b"), _case("h3", [], group="fam-c")]
    dev = [_case("d1", [], group="fam-a")]
    problems = check_leakage(held, dev)
    assert any("h1" in p and "fam-a" in p for p in problems)
    assert any("h2: exact duplicate of h1" in p or "h3: exact duplicate of h1" in p for p in problems)
    assert check_leakage([_case("x", [], question="q1"), _case("y", [], question="q2")]) == []


# --------------------------------------------------------------------------- rubric agreement
def test_kappa_matches_textbook_values():
    assert cohens_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert cohens_kappa([1, 1, 1, 1], [1, 1, 1, 1]) == 1.0           # degenerate single category
    # Classic example: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> p_o = .70, p_e = .50, kappa = .40
    a = [1] * 25 + [0] * 25
    b = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15
    assert percent_agreement(a, b) == pytest.approx(0.70)
    assert cohens_kappa(a, b) == pytest.approx(0.40)
    assert cohens_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == pytest.approx(-1.0)


def test_rubric_report_requires_all_three_criteria_and_two_reviewers():
    rows = []
    for cid, b_sound in (("c1", True), ("c2", False), ("c3", True)):
        rows.append({"case_id": cid, "reviewer_id": "A", "question_identified": True, "object_identified": True, "mathematically_sound": True})
        rows.append({"case_id": cid, "reviewer_id": "B", "question_identified": True, "object_identified": True, "mathematically_sound": b_sound})
    rep = rubric_report(rows)
    assert rep["consensus_pass_count"] == 2 and rep["disagreements"] == ["c2"]
    assert rep["agreement"]["A vs B"]["question_identified"]["kappa"] == 1.0
    assert rep["agreement"]["A vs B"]["overall"]["percent_agreement"] == pytest.approx(2 / 3, abs=1e-4)
    with pytest.raises(ValueError):
        rubric_report(rows[::2])


# --------------------------------------------------------------------------- learning gain
def _row(pid, order, cond, topic, pre, post):
    return {"participant_id": pid, "order": order, "condition": cond, "topic": topic, "pre": pre, "post": post}


def test_learning_report_paired_difference_and_threshold():
    rows = []
    for i in range(4):
        pid, order = f"P{i}", "interactive_first" if i % 2 else "prepared_first"
        rows += [_row(pid, order, "interactive", "derivatives", 40, 70), _row(pid, order, "prepared", "limits", 40, 55)]
    rep = learning_report(rows, bootstrap=200)
    assert rep["mean_gain"] == {"interactive": 30.0, "prepared": 15.0} and rep["difference_pp"] == 15.0
    assert rep["meets_threshold"] is True and rep["orders"] == {"interactive_first": 2, "prepared_first": 2}
    assert rep["design_warnings"] == []


def test_learning_report_flags_design_problems():
    rows = [_row("P1", "interactive_first", "interactive", "derivatives", 40, 70),          # missing prepared
            _row("P2", "prepared_first", "interactive", "derivatives", 40, 60), _row("P2", "prepared_first", "prepared", "derivatives", 40, 50),
            _row("P3", "prepared_first", "interactive", "limits", 40, 60), _row("P3", "prepared_first", "prepared", "derivatives", 40, 50),
            _row("P4", "prepared_first", "interactive", "limits", 40, 60), _row("P4", "prepared_first", "prepared", "derivatives", 40, 50)]
    rep = learning_report(rows, bootstrap=50)
    assert rep["participants_paired"] == 3
    w = " ".join(rep["design_warnings"])
    assert "P1: missing condition" in w and "P2: same topic" in w and "orders not balanced" in w
    with pytest.raises(ValueError):
        learning_report([_row("P9", "x", "interactive", "t", 40, 120)])


# --------------------------------------------------------------------------- seeded faults
def test_every_seeded_fault_surfaces_at_its_declared_hook():
    outcomes = run_faults(proposal_fixture(), context_packet_fixture(), scene_fixture())
    failed = [(o.fault_id, o.observed_status, o.observed_codes) for o in outcomes if not o.passed]
    assert failed == [], failed
    assert {o.hook for o in outcomes} == {"M2", "M6", "M7"} and len(outcomes) == len(FAULTS) >= 10


def test_sample_data_runs_end_to_end_and_demonstrates_the_leakage_guard():
    held = load_cases(EXAMPLES / "heldout_sample.jsonl")
    rep = run_heldout(held, load_cases(EXAMPLES / "dev_sample.jsonl"))
    assert rep.leakage, "dev sample deliberately shares a group with the held-out sample"
    assert rep.as_dict()["out_of_scope_correctly_withheld"] == 1
    assert {o.case_id for o in rep.outcomes if not o.success and o.in_scope} == {"heldout-012", "heldout-013", "heldout-014"}
