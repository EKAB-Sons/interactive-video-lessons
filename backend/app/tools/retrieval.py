"""Retrieval over the Approved Knowledge Base (retrieval half of M6).

Deliberately simple: an in-memory store of passages that have already passed
Content Ingestion and Safety, scored by term overlap. The point for the slice
is not ranking quality but *provenance discipline*: every passage carries its
source_ref, its safety report and the role `source_data`, so nothing retrieved
can ever be mistaken for an instruction downstream.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "to", "is", "in", "and", "as", "at", "it", "this", "that", "for", "on", "by", "with"}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


@dataclass
class Passage:
    passage_id: str
    source_ref: str
    text: str
    safety: dict[str, Any] = field(default_factory=lambda: {"injection_score": 0.0, "flags": []})
    quarantined: bool = False

    def as_context(self) -> dict[str, Any]:
        """The shape the context packet schema expects. Role is always source_data."""
        return {"source_ref": self.source_ref, "text": self.text, "role": "source_data", "safety": self.safety}


class ApprovedKnowledgeBase:
    def __init__(self) -> None:
        self._passages: dict[str, Passage] = {}
        self._df: Counter[str] = Counter()

    def add(self, passage: Passage) -> None:
        if passage.passage_id in self._passages:
            raise ValueError(f"duplicate passage id {passage.passage_id}")
        self._passages[passage.passage_id] = passage
        for term in set(tokenize(passage.text)):
            self._df[term] += 1

    def __len__(self) -> int:
        return len(self._passages)

    def source_refs(self) -> list[str]:
        return sorted({p.source_ref for p in self._passages.values() if not p.quarantined})

    def retrieve(self, query: str, allowed_source_refs: list[str] | None = None, k: int = 3) -> list[Passage]:
        """TF-IDF-style overlap score. Quarantined passages are never returned,
        and the caller's allowed_source_refs (the lesson's approved sources)
        bound what can be retrieved, so retrieval cannot widen the trust set."""
        q = Counter(tokenize(query))
        n = max(1, len(self._passages))
        scored = []
        for p in self._passages.values():
            if p.quarantined:
                continue
            if allowed_source_refs is not None and p.source_ref not in allowed_source_refs:
                continue
            terms = Counter(tokenize(p.text))
            score = sum(q[t] * (1 + math.log(1 + terms[t])) * math.log(1 + n / (1 + self._df[t])) for t in q if t in terms)
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda s: (-s[0], s[1].passage_id))
        return [p for _, p in scored[:k]]
