"""Verification and Policy Layer (M7).

The learned components only propose. This package decides. It is organised as
independent check layers that each append `Issue`s, followed by a policy that
turns the issues into a verdict: accept, request one
bounded revision, ask the student to clarify, or decline with a checked
fallback.
"""
from .issues import Issue, Severity
from .policy import VERIFIER_VERSION, verify_proposal
from .loop import run_with_revision
from .lesson import verify_lesson_plan

__all__ = ["Issue", "Severity", "VERIFIER_VERSION", "verify_proposal", "verify_lesson_plan", "run_with_revision"]
