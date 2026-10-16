"""Evaluation harness for held-out quality, reviewer agreement, and learning metrics.

heldout  : 90 of 100 held-out requests; unresolved in-scope requests count as failures
rubric   : three-criterion review rubric, percent agreement and Cohen's kappa between reviewers
learning : counterbalanced pre/post gain, interactive minus prepared, against the 10-pp threshold
faults   : seeded faults that must surface at the declared monitoring hook (M2/M6/M7)
"""
from .heldout import Case, HeldoutReport, RecordedPlanner, load_cases, run_heldout
from .rubric import RUBRIC, cohens_kappa, percent_agreement, rubric_report
from .learning import learning_report
from .faults import FAULTS, run_faults

__all__ = ["Case", "HeldoutReport", "RecordedPlanner", "load_cases", "run_heldout", "RUBRIC", "cohens_kappa",
           "percent_agreement", "rubric_report", "learning_report", "FAULTS", "run_faults"]
