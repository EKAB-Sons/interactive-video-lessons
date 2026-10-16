"""The issue model every check layer speaks.

Severity encodes the withhold threshold: one unresolved error that changes
the concept, result or conclusion (`blocking`); wording or formatting problems
do not stop the lesson (`warning`). `repairable` encodes whether the single
permitted revision could plausibly fix it: a wrong value can be revised, a
stale scene version cannot (the context must be rebuilt instead).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    path: str = "/"
    severity: Severity = Severity.BLOCKING
    repairable: bool = True
    layer: str = "structural"
    computed: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "path": self.path,
            "message": self.message,
            "repairable": self.repairable,
            "layer": self.layer,
        }


@dataclass
class IssueList:
    items: list[Issue] = field(default_factory=list)

    def add(self, issue: Issue) -> None:
        self.items.append(issue)

    def extend(self, issues: list[Issue]) -> None:
        self.items.extend(issues)

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.items if i.severity is Severity.BLOCKING]

    @property
    def has_blocking(self) -> bool:
        return any(i.severity is Severity.BLOCKING for i in self.items)

    @property
    def has_unrepairable(self) -> bool:
        return any(i.severity is Severity.BLOCKING and not i.repairable for i in self.items)

    def codes(self) -> list[str]:
        seen: list[str] = []
        for i in self.items:
            if i.code not in seen:
                seen.append(i.code)
        return seen
