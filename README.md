# Interactive Visual Learning Platform (Showloop)

Students pause a lesson, ask about what they selected on screen, receive a **checked** explanation branch, then return to the same lesson node. Planners only **propose** JSON; nothing is shown or committed until the **Verification and Policy Layer** accepts it.

**Repository:** [EKAB-Sons/interactive-video-lessons](https://github.com/EKAB-Sons/interactive-video-lessons)

## Backend — verification and correctness

| Component | Path | Role |
|-----------|------|------|
| Contracts and registries | `backend/app/contracts/` | JSON Schema (2020-12), operations, bounded topics |
| Mathematical tools | `backend/app/tools/` | Safe parsing, SymPy claims, approved retrieval |
| Verifier and policy | `backend/app/verification/` | Schema, scene simulation, maths, one revision, fallbacks |
| Content safety | `backend/app/safety/` | Injection scan, quarantine, output canaries |
| Service and telemetry | `backend/app/api.py`, `telemetry.py` | `/verify`, audit events (M2/M6/M7) |
| Evaluation | `backend/app/eval/` | Held-out scoring, rubric agreement, learning metrics, fault checks |
| Demo CLI | `backend/app/engine.py`, `main.py` | End-to-end interruption scenarios with a mock planner |

Planner contract: [`spec/acceptance-contract.md`](spec/acceptance-contract.md)  
Operations guide: [`docs/verification/README.md`](docs/verification/README.md)

## Quick start

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m app.main success
python -m app.main wrong_maths
uvicorn app.api:app --reload
```

Open `http://127.0.0.1:8000/docs` for the HTTP API. Accepted plans return `scene_update` with **`rendered: false`** (compiler input, not rendered video).

## Repository layout

```
spec/           acceptance contract
backend/        Python services and tests
docs/           architecture, interfaces, verification reports
examples/       safety corpus and evaluation sample data
frontend/       Flutter client (team)
```

## Integration

- **Orchestrator:** POST context, scene, and proposal to `/verify`; commit a branch only when `status` is `accepted`; pass `revision_instruction` to the planner on the first failed attempt.
- **Planners:** Emit JSON that validates against `adaptation_plan` and `operations.json`; implement `plan` and `revise`.
- **Compiler:** Apply only registry operations from an accepted `scene_update`.

Monitoring: [`docs/monitoring.md`](docs/monitoring.md).

## Not in this slice

Voice input, production model providers, rendering, full ingestion UI, and live evaluation datasets (held-out requests and study runs) are owned elsewhere or still to be collected.
