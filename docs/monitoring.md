# Monitoring

Verification owns M2, M6
and M7 and emits them through `backend/app/telemetry.py`; every event carries
`hook`, `event`, `ts`, `request_id` where applicable, and the component
versions. Other hooks are listed for completeness with their current state.
Retained evidence alone does not mean a harmful action was detected.

| Hook | Component | Measures | Emitted by | Status |
|---|---|---|---|---|
| M1 | Interactive lesson interface | input completeness, pointer mapping, transcription | app | planned |
| M2 | Content ingestion and safety | admitted / flagged / quarantined per source, max injection score | `telemetry.safety` | **emitted** |
| M3 | Base lesson planner | maths correctness, objective coverage, sequence | planner owner | planned |
| M4 | Context builder and referent resolver | referent correctness, state reconstruction | context owner | planned |
| M5 | Learned adaptation | relevance, misconception recognition | planner owner | planned |
| M6 | Retrieval and mathematical tools | one event per claim: `verified` / `mismatch` / `unparseable` / `error`, solver version | `telemetry.tools` | **emitted** |
| M7 | Verification and policy | status, attempt, reason codes, blocking/warning counts, claims verified, elapsed vs deadline, verifier/planner/config versions | `telemetry.verification` | **emitted** |
| M8 | Scene compiler and renderer | DSL validity, render completion | compiler owner | planned |
| M9 | Lesson and session state | return anchor, continuation | orchestrator | trace only (`showloop.trace`) |
| M10 | Cache and delivery | hit rate, latency | orchestrator | planned |
| M11 | End-to-end operations | stage latency, failures | orchestrator | trace only |

## Audit behaviour

- The HTTP service (`app/api.py`) is fail-closed: if the telemetry sink cannot be written, `/verify` returns 503 instead of deciding without a record.
- `IVL_TELEMETRY_PATH` selects a JSONL sink; without it an in-memory sink is used and exposed at `/telemetry/recent` for local inspection.
- Seeded-fault coverage: `python -m app.eval` runs eleven faults and checks each one surfaces at the declared hook with the declared status and reason code (`docs/verification/eval-report.md`).

## Blind spots that remain

Plausible-but-wrong explanations whose numbers happen to be right; misleading
valid visuals; semantic prompt injections without lexical markers (one in the
spike corpus); accumulated contradictions across turns. No token use or cost is
recorded yet.
