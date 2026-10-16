"""The verifier's scene simulator.

To check an operation list we must know what the scene looks like *at each
step*, because `draw_tangent` on step 2 may legitimately be referenced by
`annotate_value` on step 3. The simulator applies the registry's `creates` and
`removes` semantics to a copy of the scene. It is not the compiler: it tracks
only object existence, kind and origin, which is all the checks need.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from .. import contracts

OBJECT_ID = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_-]*$")


class SceneSimulator:
    def __init__(self, scene: dict[str, Any]) -> None:
        self.objects: dict[str, dict[str, Any]] = copy.deepcopy(scene.get("objects", {}))
        self.created: list[str] = []
        self.removed: list[str] = []

    def exists(self, object_id: str) -> bool:
        return object_id in self.objects

    def kind(self, object_id: str) -> str | None:
        obj = self.objects.get(object_id)
        return obj.get("kind") if obj else None

    def origin(self, object_id: str) -> str:
        obj = self.objects.get(object_id) or {}
        return obj.get("origin", "base")

    def apply(self, op: dict[str, Any]) -> None:
        """Apply an operation that has already passed argument checks."""
        spec = contracts.operation_spec(op.get("type", "")) or {}
        if "creates" in spec:
            object_id = op[spec["creates"]]
            new_obj: dict[str, Any] = {"kind": spec["created_kind"], "origin": "branch"}
            if spec["created_kind"] == "curve":
                new_obj.update({"expression": op.get("expression"), "var": op.get("var"), "domain": op.get("domain")})
            if spec["created_kind"] == "line":
                # A line remembers which curve it belongs to and where, so a
                # later label on that line can be checked against the right function.
                for key in ("curve", "at_x", "h"):
                    if key in op:
                        new_obj[key] = op[key]
            self.objects[object_id] = new_obj
            self.created.append(object_id)
        if "removes" in spec:
            object_id = op[spec["removes"]]
            self.objects.pop(object_id, None)
            self.removed.append(object_id)

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.objects)
