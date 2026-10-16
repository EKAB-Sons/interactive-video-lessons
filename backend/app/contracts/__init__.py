"""Contract loading and schema validation.

The JSON Schemas and registries in this package are the single source of truth
shared by the planners (who emit plans), the compiler (who consumes accepted
plans) and the verifier (who decides). Python code never redefines them; it
loads them from disk so that a change to a schema is a change everyone sees.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACTS_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = CONTRACTS_DIR / "schemas"

SCHEMA_NAMES = (
    "claim",
    "context_packet",
    "scene_graph",
    "adaptation_plan",
    "lesson_plan",
    "verification_result",
    "revision_instruction",
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=None)
def schema(name: str) -> dict[str, Any]:
    if name not in SCHEMA_NAMES:
        raise KeyError(f"unknown schema {name!r}; known: {SCHEMA_NAMES}")
    return _load_json(SCHEMA_DIR / f"{name}.schema.json")


@lru_cache(maxsize=None)
def _registry() -> Registry:
    resources = []
    for name in SCHEMA_NAMES:
        doc = schema(name)
        resource = Resource.from_contents(doc)
        # Register under both the full $id and the bare filename so that
        # relative "$ref": "claim.schema.json" resolves from any sibling schema.
        resources.append((doc["$id"], resource))
        resources.append((f"{name}.schema.json", resource))
    return Registry().with_resources(resources)


@lru_cache(maxsize=None)
def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(schema(name), registry=_registry())


def validation_errors(name: str, instance: Any) -> list[dict[str, str]]:
    """Return schema violations as plain dicts, sorted by path, so callers can
    turn them into issues without depending on jsonschema's error objects."""
    errors = []
    for err in sorted(validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path)):
        path = "/" + "/".join(str(p) for p in err.absolute_path)
        errors.append({"path": path, "message": err.message, "validator": err.validator})
    return errors


_KIND_TO_DEF = {"adaptation_proposal": "proposal", "clarification": "clarification", "failure": "failure"}


@lru_cache(maxsize=None)
def _kind_validator(kind: str) -> Draft202012Validator:
    """A validator for one branch of the adaptation_plan oneOf, so that errors
    point at the offending field instead of a root-level 'not valid under any
    of the given schemas'."""
    sub = {"$schema": "https://json-schema.org/draft/2020-12/schema",
           "$ref": f"{schema('adaptation_plan')['$id']}#/$defs/{_KIND_TO_DEF[kind]}"}
    return Draft202012Validator(sub, registry=_registry())


def plan_validation_errors(instance: Any) -> list[dict[str, str]]:
    """Validate a planner response. Uses the declared kind to pick the precise
    branch; falls back to the full oneOf when the kind is missing or unknown."""
    kind = instance.get("kind") if isinstance(instance, dict) else None
    if kind not in _KIND_TO_DEF:
        return validation_errors("adaptation_plan", instance)
    errors = []
    for err in sorted(_kind_validator(kind).iter_errors(instance), key=lambda e: list(e.absolute_path)):
        path = "/" + "/".join(str(p) for p in err.absolute_path)
        errors.append({"path": path, "message": err.message, "validator": err.validator})
    return errors


@lru_cache(maxsize=None)
def operations_registry() -> dict[str, Any]:
    return _load_json(CONTRACTS_DIR / "operations.json")


@lru_cache(maxsize=None)
def topics_registry() -> dict[str, Any]:
    return _load_json(CONTRACTS_DIR / "topics.json")


def operation_spec(op_type: str) -> dict[str, Any] | None:
    return operations_registry()["operations"].get(op_type)


def topic_spec(topic: str) -> dict[str, Any] | None:
    return topics_registry()["topics"].get(topic)
