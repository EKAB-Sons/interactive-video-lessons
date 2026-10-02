# Interactive Visual Learning Platform

## Prosit 1 framing and runnable stub

We are framing this platform as a student-controlled visual lesson: a student pauses a lesson, asks by text/voice/pointer, receives an explanation connected to the current scene, and resumes coherently. In our derivative fixture, the student selects `graph.tangent` on a distance–time graph and asks why its slope is instantaneous speed. The proposed branch shows a secant approaching the tangent, then returns to the saved lesson node.

This repository is deliberately narrow. It does not implement voice recognition, ingestion, a real provider, rendering, student data, or educational evaluation. The learned planning boundary is exactly the **Base Lesson Planning Engine** and **Lesson Adaptation Builder**. Both propose plans; they cannot render, commit state, or send unchecked content. A hosted Foundation Model Provider is outside our platform boundary.

| Capability | Status |
|---|---|
| Derivatives graph, object IDs, context packet, checks, branch/return, JSONL trace | Implemented local stub |
| Planner output | Deterministic mock (`mock-planner`, no API key) |
| Animation, speech, retrieval, ingestion, real provider, evaluation | Planned |

The stub demonstrates state-safe interruption handling, not rendering or learning benefit. It cannot establish educational effectiveness or provider safety.

## Run

From a fresh checkout with Python 3.10+:

```powershell
cd backend
python -m app.main success --trace ..\examples\derivatives-demo.jsonl
python -m app.main unknown
python -m app.main malformed
python -m app.main unsupported
python -m app.main stale
python -m app.main timeout
python -m unittest discover -s tests -v
python -m compileall app
```

The committed trace is generated from team-authored fixture content. `scene_update.rendered` is always `false`: it is checked compiler input, not an animation. See [architecture](docs/architecture/README.md), [contracts](docs/interfaces/contracts.md), [monitoring](docs/monitoring.md), [decisions](docs/decisions.md), [source inventory](docs/prosit-1/README.md), and [open issues](docs/open-issues.md). Prosit 2 must bound topics/operations, select a provider and verification approach, settle data permissions, and define recruitment/comparators.

## Architecture & Technical Scope

### Learner Experience
An Interactive Lesson App connected via HTTPS and realtime channels through an API Gateway.

### Platform Services
- Session and Lesson Orchestrator
- Base Lesson Planning Engine
- Verification and Policy Layer
- Lesson and Scene Compiler
- Content Ingestion and Safety
- Learned Adaptation Component
- Context Builder
- Asset Delivery Service

### Infrastructure
- Rendering Job Queue
- Approved Knowledge Base
- Asset Cache
- Telemetry Store
- Foundation Model Provider
- Lesson Scene/Session State Database

### Measurement & Evaluation
The system relies on a formalized measurement stub matrix to track degradation signals, ensuring:
- Interaction mapping completeness
- Malicious content detection
- Mathematical correctness
- Accurate referent resolution
- Reliable end-to-end rendering

## Repository Structure

- `spec/`: Scope and architecture specifications.
- `backend/`: Python-based API (using FastAPI) handling the learned components and orchestrator.
- `frontend/`: Cross-platform client (using Flutter) serving as the Interactive Lesson App.
- `.github/workflows/`: CI/CD pipelines enforcing Test-Driven Development (TDD).
