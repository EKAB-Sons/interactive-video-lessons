import argparse, json
from pathlib import Path
from .engine import run_interruption
def main():
 p=argparse.ArgumentParser(); p.add_argument("scenario", nargs="?", default="success", choices=["success","unknown","ambiguous","malformed","unsupported","stale","timeout"]); p.add_argument("--trace", type=Path); a=p.parse_args()
 result=run_interruption(selected_object_id="missing.object" if a.scenario=="unknown" else "graph.tangent", scenario=a.scenario)
 lines="\n".join(json.dumps(event, sort_keys=True) for event in result["events"])+"\n"
 if a.trace:
  a.trace.parent.mkdir(parents=True, exist_ok=True)
  a.trace.write_text(lines, encoding="utf-8")
 print(json.dumps({"status":result["status"],"reason":result["reason"],"events":len(result["events"])}, sort_keys=True))
if __name__ == "__main__": main()
