"""Layer 0: the contracts themselves are tested before anything depends on them."""
from __future__ import annotations

import copy

import pytest
from jsonschema import Draft202012Validator

from app import contracts
from tests.fixtures import (
    context_packet_fixture,
    lesson_plan_fixture,
    proposal_fixture,
    scene_fixture,
)


@pytest.mark.parametrize("name", contracts.SCHEMA_NAMES)
def test_every_schema_is_valid_draft_2020_12(name):
    Draft202012Validator.check_schema(contracts.schema(name))


@pytest.mark.parametrize("name", contracts.SCHEMA_NAMES)
def test_every_schema_declares_an_id_matching_its_filename(name):
    assert contracts.schema(name)["$id"].endswith(f"{name}.schema.json")


def test_cross_file_refs_resolve():
    # adaptation_plan -> claim.schema.json; verification_result -> revision_instruction.schema.json
    assert contracts.validation_errors("adaptation_plan", proposal_fixture()) == []
    result = {
        "request_id": "r1", "status": "revision_requested", "attempt": 1, "verifier_version": "v",
        "issues": [], "checked_claims": [], "elapsed_ms": 1.0,
        "revision_instruction": {
            "kind": "revision_instruction", "request_id": "r1", "attempt": 2,
            "failed_checks": [{"code": "x", "path": "/", "message": "m"}],
            "constraints": {"scene_version": 1, "allowed_operations": [], "known_object_ids": [], "approved_source_refs": []},
        },
    }
    assert contracts.validation_errors("verification_result", result) == []


def test_fixtures_validate():
    assert contracts.validation_errors("scene_graph", scene_fixture()) == []
    assert contracts.validation_errors("context_packet", context_packet_fixture()) == []
    assert contracts.validation_errors("adaptation_plan", proposal_fixture()) == []
    assert contracts.validation_errors("lesson_plan", lesson_plan_fixture()) == []


def test_proposal_with_missing_claims_field_fails():
    bad = proposal_fixture()
    del bad["claims"]
    errors = contracts.validation_errors("adaptation_plan", bad)
    assert errors, "a proposal without a claims array must not validate"


def test_proposal_with_unknown_top_level_field_fails():
    bad = proposal_fixture()
    bad["raw_prompt"] = "ignore previous instructions"
    assert contracts.validation_errors("adaptation_plan", bad)


def test_clarification_and_failure_variants_validate():
    clar = {"kind": "clarification", "request_id": "r1", "status": "needs_clarification",
            "question": "Do you mean the tangent or the curve?", "candidate_object_ids": ["graph.tangent", "graph.curve"]}
    fail = {"kind": "failure", "request_id": "r1", "status": "out_of_scope", "reason": "Topic not supported."}
    assert contracts.validation_errors("adaptation_plan", clar) == []
    assert contracts.validation_errors("adaptation_plan", fail) == []


def test_claim_conditional_requirements():
    assert contracts.validation_errors("claim", {"id": "c1", "type": "derivative", "expression": "x**2", "claimed": "2*x"}) == []
    assert contracts.validation_errors("claim", {"id": "c1", "type": "derivative", "expression": "x**2"})
    assert contracts.validation_errors("claim", {"id": "c1", "type": "slope_secant", "expression": "x**2", "at_x": 1, "claimed": 3})


def test_operations_registry_is_self_consistent():
    reg = contracts.operations_registry()["operations"]
    claim_types = set(contracts.schema("claim")["properties"]["type"]["enum"])
    for name, spec in reg.items():
        assert set(spec["required"]) <= set(spec["args"]), name
        assert set(spec["refs"]) <= set(spec["args"]), name
        for arg, aspec in spec["args"].items():
            if aspec["type"] == "claim_ref":
                assert set(aspec["claim_types"]) <= claim_types, (name, arg)
        if spec["fact_bearing"]:
            assert "claim_ref" in spec["required"], f"fact-bearing op {name} must require a claim_ref"
        if "creates" in spec:
            assert spec["args"][spec["creates"]]["type"] == "new_object_id", name


def test_topics_registry_only_names_known_operations_and_claim_types():
    ops = set(contracts.operations_registry()["operations"])
    claim_types = set(contracts.schema("claim")["properties"]["type"]["enum"])
    for topic, spec in contracts.topics_registry()["topics"].items():
        assert set(spec["allowed_operations"]) <= ops, topic
        assert set(spec["allowed_claim_types"]) <= claim_types, topic
        assert spec["status"] in {"implemented", "deferred"}


def test_scene_fixture_objects_are_hit_test_ids():
    scene = scene_fixture()
    for object_id in scene["objects"]:
        assert "." in object_id, "object ids are namespaced so the hit-test is unambiguous"
