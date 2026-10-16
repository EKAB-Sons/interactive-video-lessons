"""Content safety: the ingestion half owned by verification (M2) and the
output-side leak check (M7).

An uploaded or retrieved passage is data. It is never an instruction. These
modules make that distinction operational: normalise, score, quarantine at
ingestion; detect obeyed instructions at the output with canaries.
"""
from .scan import SafetyReport, scan_passage, normalise
from .policy import QUARANTINE_THRESHOLD, admit_passages
from .canary import CanaryRegistry, leak_check

__all__ = ["SafetyReport", "scan_passage", "normalise", "QUARANTINE_THRESHOLD", "admit_passages", "CanaryRegistry", "leak_check"]
