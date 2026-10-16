"""CLI entrypoint: run mock-planner scenarios through the verifier and optional JSONL trace."""
import argparse
import json
from pathlib import Path

from .engine import run_interruption

SCENARIOS = ["success", "unknown", "ambiguous", "malformed", "unsupported", "stale", "timeout", "wrong_maths", "wrong_twice"]


def main() -> None:
    p = argparse.ArgumentParser(description="Run one checked lesson interruption through the verifier.")
    p.add_argument("scenario", nargs="?", default="success", choices=SCENARIOS)
    p.add_argument("--trace", type=Path, help="write the JSONL trace here")
    a = p.parse_args()
    result = run_interruption(selected_object_id="missing.object" if a.scenario == "unknown" else "graph.tangent", scenario=a.scenario)
    lines = "\n".join(json.dumps(event, sort_keys=True, default=str) for event in result["events"]) + "\n"
    if a.trace:
        a.trace.parent.mkdir(parents=True, exist_ok=True)
        a.trace.write_text(lines, encoding="utf-8")
    summary = {"status": result["status"], "reason": result["reason"], "events": len(result["events"])}
    if "fallback" in result:
        summary["fallback"] = result["fallback"]["kind"]
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
