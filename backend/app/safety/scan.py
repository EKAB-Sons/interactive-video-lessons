"""Injection scanner for uploaded and retrieved text.

Design: a small set of *independent signals*, each with a weight, combined
into a score in [0, 1]. Signals are chosen so that ordinary maths text (which
is full of imperatives like "let", "consider", "ignore the sign") scores low,
while text that addresses the model, changes roles, references a system
prompt, hides content, or tries to exfiltrate scores high. Normalisation runs
first so that zero-width characters, homoglyphs and HTML comments cannot hide
an instruction from the patterns.

This is a heuristic filter, not a proof. The injection spike (scripts/
injection_spike.py) measures its recall and false-positive rate against a
corpus, and the output-side canary check catches what it misses.
"""
from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field

SCANNER_VERSION = "scan-v1"

# Zero-width and bidi control characters used to hide or reorder text.
_HIDDEN = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069\u00ad]")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HTML_TAG = re.compile(r"<[^>]{1,80}>")
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^\s\n]*?)\)(?=\s|$)")
_HOMOGLYPHS = str.maketrans({
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0443": "y", "\u0445": "x",  # Cyrillic
    "\u0456": "i", "\u0458": "j", "\u04bb": "h", "\u0501": "d", "\u051b": "q", "\u051d": "w",
    "\u03bf": "o", "\u03b1": "a", "\u03b5": "e", "\u03c1": "p", "\u03c5": "u", "\u03bd": "v",  # Greek
    "\u2024": ".", "\u2027": ".",
})

# Each signal: (name, compiled pattern, weight). Weights are not probabilities;
# they are tuned on the spike corpus so that one strong signal (>= 0.6) or two
# medium signals (~0.35 each) cross the quarantine threshold.
_SIGNALS: list[tuple[str, re.Pattern[str], float]] = [
    ("override_instructions", re.compile(r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|your|the)\b[^.\n]{0,30}\b(instructions?|prompts?|rules?|guidelines?|directions?)\b", re.I), 0.7),
    ("role_change", re.compile(r"\b(you are now|act as|pretend (to be|you are)|from now on,? you|your new (role|task|instructions?)|switch to .{0,20}mode|developer mode|jailbreak)\b", re.I), 0.6),
    ("system_prompt_ref", re.compile(r"\b(system (prompt|message|instructions?)|hidden (prompt|instructions?)|initial prompt|BEGIN SYSTEM|END SYSTEM)\b", re.I), 0.6),
    ("model_addressed", re.compile(r"\b(dear|hey|hello|attention|note to)?\s*(ai|assistant|model|chatbot|tutor|gpt|claude|llm|language model)\b[^.\n]{0,20}\b(you must|you should|you will|always|never|do not|don't|please)\b", re.I), 0.5),
    ("exfiltration", re.compile(r"\b(reveal|print|output|repeat|leak|show me|send|include)\b[^.\n]{0,40}\b(system prompt|instructions|api key|secret|password|token|canary|hidden text|conversation history)\b", re.I), 0.6),
    ("teach_falsehood", re.compile(r"\b(tell|teach|convince|inform)\b[^.\n]{0,30}\b(students?|learners?|users?|the user)\b[^.\n]{0,40}\b(that|to)\b", re.I), 0.35),
    ("chat_template_tokens", re.compile(r"(<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>|\[INST\]|\[/INST\]|<<SYS>>|### (System|Instruction|Human|Assistant):)", re.I), 0.7),
    ("imperative_to_tool", re.compile(r"\b(call|invoke|run|execute)\b[^.\n]{0,20}\b(the )?(tool|function|command|operation)\b", re.I), 0.4),
    # Naming one of our own scene operations inside uploaded notes is strong evidence of targeting the DSL.
    ("dsl_operation_named", re.compile(r"\b(remove_object|plot_function|set_narration|draw_tangent|draw_secant|show_secant_sequence|annotate_value|add_label|unhighlight)\b", re.I), 0.6),
    ("answer_key_bait", re.compile(r"\b(the )?(correct |right |final )?answer( key)?\s*(is|:|to .{0,30} is)[^.\n]{0,25}\b(always|regardless|no matter)\b", re.I), 0.5),
    ("urgency_secrecy", re.compile(r"\b(do not (tell|mention|reveal) (this|the user|the student|students?|learners?|anyone)|keep this (secret|hidden)|without (telling|informing) (the )?(user|student))\b", re.I), 0.6),
]
# Checked on the text *before* HTML tags are stripped, otherwise <script> would vanish.
_RAW_SIGNALS: list[tuple[str, re.Pattern[str], float]] = [
    ("url_or_script", re.compile(r"(javascript:|data:text/html|<script\b|onerror=|onload=)", re.I), 0.6),
]
_BASE64_BLOB = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{48,}={0,2}(?![A-Za-z0-9+/=])")


@dataclass
class SafetyReport:
    scanner_version: str
    injection_score: float
    flags: list[str] = field(default_factory=list)
    normalised_text: str = ""
    hidden_chars_removed: int = 0
    decoded_blobs: int = 0

    def as_dict(self) -> dict:
        return {"scanner_version": self.scanner_version, "injection_score": round(self.injection_score, 3),
                "flags": list(self.flags), "hidden_chars_removed": self.hidden_chars_removed, "decoded_blobs": self.decoded_blobs}


def normalise(text: str) -> tuple[str, int, int]:
    """NFKC-fold, strip hidden characters, map common homoglyphs, surface HTML
    comments and link targets, and decode long base64 blobs so that their
    content is scanned too. Returns (text, hidden_chars_removed, decoded_blobs)."""
    folded = unicodedata.normalize("NFKC", text or "")
    hidden = len(_HIDDEN.findall(folded))
    folded = _HIDDEN.sub("", folded).translate(_HOMOGLYPHS)
    folded = _HTML_COMMENT.sub(lambda m: " " + m.group(0)[4:-3] + " ", folded)
    folded = _MD_LINK.sub(lambda m: f"{m.group(1)} {m.group(2)} ", folded)
    folded = _HTML_TAG.sub(" ", folded)
    decoded = 0
    def _decode(m: re.Match[str]) -> str:
        nonlocal decoded
        try:
            raw = base64.b64decode(m.group(0) + "=" * (-len(m.group(0)) % 4), validate=False)
            txt = raw.decode("utf-8")
            if txt.isprintable() or "\n" in txt:
                decoded += 1
                return f" {txt} "
        except Exception:
            pass
        return m.group(0)
    folded = _BASE64_BLOB.sub(_decode, folded)
    return folded, hidden, decoded


def scan_passage(text: str) -> SafetyReport:
    normalised, hidden, decoded = normalise(text)
    flags: list[str] = []
    score = 0.0
    raw_folded = unicodedata.normalize("NFKC", text or "")
    for name, pattern, weight in _RAW_SIGNALS:
        if pattern.search(raw_folded):
            flags.append(name)
            score = 1 - (1 - score) * (1 - weight)
    for name, pattern, weight in _SIGNALS:
        if pattern.search(normalised):
            flags.append(name)
            score = 1 - (1 - score) * (1 - weight)   # noisy-OR: independent signals accumulate
    if hidden >= 3:
        flags.append("hidden_characters")
        score = 1 - (1 - score) * (1 - 0.4)
    if decoded:
        flags.append("encoded_content")
        score = 1 - (1 - score) * (1 - 0.3)
    return SafetyReport(SCANNER_VERSION, min(1.0, score), flags, normalised, hidden, decoded)
