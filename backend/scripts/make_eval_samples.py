"""Generate SYNTHETIC sample data for the evaluation harness.

Nothing here is a real student request, review or score. The files exist so the
harness can be run end-to-end and read by the team before real held-out
requests, reviewer labels and study data are collected. Every record is tagged synthetic.

    python -m scripts.make_eval_samples        (from backend/)
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

from tests.fixtures import SOURCE, context_packet_fixture, proposal_fixture, scene_fixture

OUT = Path(__file__).resolve().parents[2] / "examples" / "eval"


def _case(i: int, group: str, question: str, selected: str, attempts, *, in_scope=True, notes="", at_x=None, h_values=None,
          claimed=None, scene_version=7):
    ctx = context_packet_fixture(request_id=f"heldout-{i:03d}", question_text=question, selected_object_ids=[selected], scene_version=scene_version)
    scene = scene_fixture()
    scene["scene_version"] = scene_version
    fixed = []
    for a in attempts:
        if a == "timeout":
            fixed.append(a)
            continue
        a = copy.deepcopy(a)
        a["request_id"] = ctx["request_id"]
        if a["kind"] == "adaptation_proposal":
            a["scene_version"] = scene_version
            a["return_anchor"]["scene_version"] = scene_version
            a["interpretation"]["referents"] = [selected]
        fixed.append(a)
    return {"case_id": f"heldout-{i:03d}", "group_id": group, "in_scope": in_scope, "synthetic": True, "notes": notes,
            "context": ctx, "scene": scene, "attempts": fixed}


def good(at_x=2.0, h=(1, 0.5, 0.1, 0.01)):
    p = proposal_fixture()
    slope, sec = 2 * at_x, 2 * at_x + h[0]
    p["claims"] = [
        {"id": "c1", "type": "slope_tangent", "expression": "t**2", "var": "t", "at_x": at_x, "claimed": slope},
        {"id": "c2", "type": "secant_converges", "expression": "t**2", "var": "t", "at_x": at_x, "h_values": list(h)},
        {"id": "c3", "type": "slope_secant", "expression": "t**2", "var": "t", "at_x": at_x, "h": h[0], "claimed": sec},
    ]
    p["operations"][1].update(at_x=at_x, h_values=list(h))
    p["operations"][2] = {"type": "draw_tangent", "object_id": "graph.tangent2", "curve": "graph.curve", "at_x": at_x, "claim_ref": "c1"} if at_x != 2 else p["operations"][2]
    return p


def wrong():
    p = good()
    p["claims"][0]["claimed"] = 5
    return p


def clarification(i):
    return {"kind": "clarification", "request_id": f"heldout-{i:03d}", "status": "needs_clarification",
            "question": "Do you mean the tangent or the curve?", "candidate_object_ids": ["graph.tangent", "graph.curve"]}


def heldout():
    qs = ["Why is the slope of this line the instantaneous speed?", "What does this line's steepness tell us?",
          "How is the gradient here related to velocity?", "Is this the speed at exactly t = 2?",
          "Why do we need a tangent rather than a secant?", "What happens to the secant as h gets small?",
          "Could you show how the secant approaches this line?", "Why is the slope 4 and not 5?"]
    cases = [_case(i + 1, f"family-tangent-{i % 4}", q, "graph.tangent", [good()]) for i, q in enumerate(qs)]
    cases.append(_case(9, "family-point-1", "What is the slope at t = 1?", "graph.curve", [good(at_x=1.0)]))
    cases.append(_case(10, "family-point-3", "And at t = 3?", "graph.curve", [good(at_x=3.0)]))
    cases.append(_case(11, "family-repair", "Why is this slope 4?", "graph.tangent", [wrong(), good()], notes="wrong first, repaired"))
    cases.append(_case(12, "family-repair", "So the instantaneous speed is 4?", "graph.tangent", [wrong(), wrong()], notes="wrong twice -> failure"))
    cases.append(_case(13, "family-clarify", "What about this?", "graph.tangent", [clarification(13)], notes="in-scope clarification counts as failure"))
    cases.append(_case(14, "family-timeout", "Why is the slope the speed?", "graph.tangent", ["timeout"], notes="planner timeout -> failure"))
    oos = good()
    oos["claims"].append({"id": "c9", "type": "integral", "expression": "t**2", "var": "t", "claimed": "t**3/3"})
    cases.append(_case(15, "family-oos", "What is the area under the curve?", "graph.curve", [oos, oos], in_scope=False, notes="integral is out of the bounded topic"))
    return cases


def dev():
    return [_case(901, "family-tangent-0", "Why is the slope the speed here?", "graph.tangent", [good()]),
            _case(902, "family-dev-only", "Slope at t = 2?", "graph.tangent", [good()])]


def rubric_labels(cases):
    rng = random.Random(7)
    rows = []
    for c in cases:
        truth = c["in_scope"] and c["notes"] not in ("wrong twice -> failure", "in-scope clarification counts as failure", "planner timeout -> failure")
        for reviewer in ("reviewer-A", "reviewer-B"):
            flip = reviewer == "reviewer-B" and rng.random() < 0.1
            rows.append({"case_id": c["case_id"], "reviewer_id": reviewer, "synthetic": True,
                         "question_identified": truth, "object_identified": truth, "mathematically_sound": truth != flip})
    return rows


def learning():
    rng = random.Random(11)
    rows = []
    for i in range(24):
        pid, order = f"P{i + 1:02d}", "interactive_first" if i % 2 == 0 else "prepared_first"
        topics = ("derivatives", "limits") if i % 4 < 2 else ("limits", "derivatives")
        for cond, topic in zip(("interactive", "prepared"), topics):
            pre = rng.randint(20, 55)
            gain = rng.gauss(32 if cond == "interactive" else 20, 9)
            rows.append({"participant_id": pid, "order": order, "condition": cond, "topic": topic, "synthetic": True,
                         "pre": pre, "post": max(0, min(100, round(pre + gain)))})
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    hold = heldout()
    for name, rows in (("heldout_sample.jsonl", hold), ("dev_sample.jsonl", dev()),
                       ("rubric_labels_sample.jsonl", rubric_labels(hold)), ("learning_sample.jsonl", learning())):
        (OUT / name).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        print(f"wrote {len(rows):3d} rows -> {OUT / name}")


if __name__ == "__main__":
    main()
