# Verification, correctness tooling, and evaluation

Verification and Policy Layer, mathematical tools, content-safety ingestion checks, degradation handling, and the evaluation harness for Showloop.

## Layout

```
backend/app/
  contracts/        schemas, operations.json, topics.json
  tools/            expressions.py, solver.py, retrieval.py
  verification/     checks, policy, loop, fallbacks, lesson verification
  safety/           scan.py, admission policy, canary.py
  telemetry.py      M2 / M6 / M7 events
  api.py            FastAPI service
  eval/             heldout, rubric, learning, faults
  engine.py, main.py   local demo flow on the verifier
backend/scripts/    injection_spike.py, make_eval_samples.py
backend/tests/      pytest suite
examples/safety/    injection corpus
examples/eval/      sample JSONL for the harness
spec/acceptance-contract.md
```

## Run

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest
python -m app.main wrong_maths
python -m scripts.injection_spike
python -m app.eval ../examples/eval ../docs/verification/eval-report.md
uvicorn app.api:app --reload
```

## Recorded results

| Measure | Value | Location |
|---------|-------|----------|
| Automated tests | 240 passing | `pytest` |
| Injection scanner recall / FPR | 29/30, 0/30 benign quarantined | `injection-spike-results.md` |
| Seeded monitoring faults | 11/11 | `eval-report.md` |

Sample data under `examples/eval/` is synthetic until production evaluation sets are collected.

## Limits

The injection scanner is heuristic; canary and narration checks are backstops. The solver covers the bounded **derivatives** topic. The verifier judges plans, not rendered pixels.
