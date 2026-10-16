"""Output-side leak detection with canaries.

A scanner can miss an instruction. If a planner then obeys it, the evidence is
in the output: the planner emits text or operations it was told to emit. We
plant canary tokens in test passages ("...include the word ORCHID-7731...") and
check every outgoing proposal for them. In production the same check runs
against (a) the registry of canaries planted in red-team fixtures and (b) any
quarantined passage's distinctive phrases, so a leak lights up M7 even when
M2 was silent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..verification.issues import Issue


@dataclass
class CanaryRegistry:
    tokens: set[str] = field(default_factory=set)

    def plant(self, token: str) -> str:
        self.tokens.add(token)
        return token

    def extend(self, tokens: Iterable[str]) -> None:
        self.tokens.update(tokens)


def _texts(proposal: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not isinstance(proposal, dict):
        return out
    for i, op in enumerate(proposal.get("operations", []) or []):
        for key in ("text", "label_text"):
            if isinstance(op.get(key), str):
                out.append((f"/operations/{i}/{key}", op[key]))
    interp = proposal.get("interpretation") or {}
    for key in ("question_summary", "misconception"):
        if isinstance(interp.get(key), str):
            out.append((f"/interpretation/{key}", interp[key]))
    for key in ("question", "reason"):
        if isinstance(proposal.get(key), str):
            out.append((f"/{key}", proposal[key]))
    return out


def leak_check(proposal: dict[str, Any], registry: CanaryRegistry) -> list[Issue]:
    issues: list[Issue] = []
    if not registry.tokens:
        return issues
    pattern = re.compile("|".join(re.escape(t) for t in sorted(registry.tokens, key=len, reverse=True)), re.I)
    for path, text in _texts(proposal):
        m = pattern.search(text)
        if m:
            issues.append(Issue("canary_leaked", f"output contains planted token {m.group(0)!r}: an injected instruction was obeyed",
                                path, repairable=False, layer="safety"))
    return issues
