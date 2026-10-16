"""Learning gain analysis for a counterbalanced interactive vs prepared study.

Each participant studies two matched topics, one with the interactive lesson
and one with the prepared lesson, in one of two orders. Each row is one
participant x condition with pre and post scores on a 0-100 scale:

    {"participant_id", "order": "interactive_first"|"prepared_first", "condition", "topic", "pre", "post"}

We report mean gain per condition, the paired difference (interactive minus
prepared) in percentage points, a seeded bootstrap interval for that
difference, and the design checks that make the comparison fair: balanced
orders, every participant in both conditions, and no participant seeing the
same topic twice. The 10-pp threshold is a project hypothesis, not a proof.
"""
from __future__ import annotations

import random
from statistics import mean, pstdev
from typing import Any, Iterable

THRESHOLD_PP = 10.0
CONDITIONS = ("interactive", "prepared")


def learning_report(rows: Iterable[dict[str, Any]], *, seed: int = 0, bootstrap: int = 2000) -> dict[str, Any]:
    rows = list(rows)
    by_participant: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        if r["condition"] not in CONDITIONS:
            raise ValueError(f"unknown condition {r['condition']!r}")
        if not (0 <= r["pre"] <= 100 and 0 <= r["post"] <= 100):
            raise ValueError(f"scores must be 0-100: {r}")
        by_participant.setdefault(r["participant_id"], {})[r["condition"]] = r

    design = []
    complete = {p: c for p, c in by_participant.items() if set(c) == set(CONDITIONS)}
    for p, c in by_participant.items():
        if set(c) != set(CONDITIONS):
            design.append(f"{p}: missing condition(s) {sorted(set(CONDITIONS) - set(c))}; excluded from paired analysis")
        elif c["interactive"]["topic"] == c["prepared"]["topic"]:
            design.append(f"{p}: same topic in both conditions (repeated exposure)")
        if len({r["order"] for r in c.values()}) > 1:
            design.append(f"{p}: inconsistent order labels")
    orders = [next(iter(c.values()))["order"] for c in complete.values()]
    counts = {o: orders.count(o) for o in sorted(set(orders))}
    if len(complete) > 1 and (len(counts) < 2 or abs(list(counts.values())[0] - list(counts.values())[1]) > 1):
        design.append(f"orders not balanced: {counts}")

    gains = {cond: [c[cond]["post"] - c[cond]["pre"] for c in complete.values()] for cond in CONDITIONS}
    paired = [c["interactive"]["post"] - c["interactive"]["pre"] - (c["prepared"]["post"] - c["prepared"]["pre"]) for c in complete.values()]
    rng = random.Random(seed)
    boot = sorted(mean(rng.choices(paired, k=len(paired))) for _ in range(bootstrap)) if paired else []
    ci = (boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot)) - 1]) if boot else (None, None)

    per_order = {}
    for order in counts:
        sub = [c for c in complete.values() if next(iter(c.values()))["order"] == order]
        per_order[order] = {cond: round(mean(c[cond]["post"] - c[cond]["pre"] for c in sub), 2) for cond in CONDITIONS}

    diff = mean(paired) if paired else None
    return {
        "participants_total": len(by_participant), "participants_paired": len(complete), "orders": counts,
        "mean_gain": {cond: round(mean(g), 2) if g else None for cond, g in gains.items()},
        "sd_gain": {cond: round(pstdev(g), 2) if g else None for cond, g in gains.items()},
        "difference_pp": round(diff, 2) if diff is not None else None,
        "bootstrap_95ci_pp": [round(ci[0], 2), round(ci[1], 2)] if ci[0] is not None else None,
        "threshold_pp": THRESHOLD_PP,
        "meets_threshold": diff is not None and diff >= THRESHOLD_PP,
        "ci_excludes_zero": ci[0] is not None and ci[0] > 0,
        "gain_by_order": per_order,
        "design_warnings": design,
    }
