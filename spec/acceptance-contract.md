# Acceptance contract for planner output

Status: proposed for team sign-off. Supersedes the early inline Python checks
documented in `docs/interfaces/contracts.md`.

## 1. Principle

The learned components (Base Lesson Planning Engine, Lesson Adaptation Builder)
**only propose**. They return JSON. Nothing they return is rendered, committed
to session state, or shown to a student until the Verification and Policy Layer
has produced a verdict. "Tokens for what is true, pixels for what it looks like":
every fact a plan shows or says must be carried by a *claim* that the solver has
verified; the planner may choose presentation, not truth.

## 2. Inputs the verifier judges against

| Input | Source | Why it is needed |
|---|---|---|
| `adaptation_plan` (proposal, clarification or failure) | planner | the thing being judged |
| `context_packet` | Context Builder | request_id, scene_version, selected objects, approved `source_refs`, `deadline_ms` |
| scene snapshot | Session state | live object ids and kinds, `scene_version`, lesson `nodes`, `topic`, approved `source_refs` |

The verifier is stateless: all three travel with each request, so a stale copy
cannot hide inside the verifier.

## 3. What a proposal must contain

Schema: `backend/app/contracts/schemas/adaptation_plan.schema.json` (`$defs/proposal`).

- `kind: "adaptation_proposal"`, `request_id`, `attempt` (1 or 2), `planner_id`, `config_version`, `scene_version`
- `interpretation.question_summary` and `interpretation.referents` (object ids the planner believes the student meant)
- `source_refs`: a subset of the approved refs for this lesson
- `claims[]`: typed mathematical statements (`claim.schema.json`): `derivative`, `value_at`, `slope_tangent`, `slope_secant`, `limit`, `equivalent`, `secant_converges`
- `operations[]` (1–40) from the registry `backend/app/contracts/operations.json`; fact-bearing operations carry `claim_ref`
- `return_anchor {node_id, scene_version}`

Narration and labels state numbers only through `{{claim:<id>}}` placeholders.
The verifier substitutes the solver's value, never the planner's.

## 4. Verdicts

| Status | Meaning | What the student path does |
|---|---|---|
| `accepted` | all checks pass | `scene_update` (rendered=false) goes to the compiler; branch committed |
| `revision_requested` | attempt 1 failed with only repairable issues | planner gets a `revision_instruction`; exactly one retry |
| `declined` | attempt 2 still fails, or the planner timed out / errored | checked `fallback` (text built only from verified claims) |
| `rejected` | an unrepairable issue (stale version, wrong request, out-of-scope topic, instruction marker, canary leak) | no retry; fallback or decline |
| `needs_clarification` | the planner (or the verifier) cannot resolve the referent | student asked one question |
| `degraded` | the 10 s budget is already spent | fallback offering wait / retry / return |

`MAX_ATTEMPTS = 2`. The verifier, not the planner, stamps `attempt = 2` on the revision.

## 5. Check order and issue model

```
deadline -> schema/kind -> topic & binding (unrepairable) -> interpretation -> sources
        -> claims (solver) -> operations on a simulated scene -> narration discipline -> verdict
```

Every finding is an `Issue{code, path, message, severity, repairable, layer, computed}`.
`blocking` issues stop acceptance; `warning` issues are logged. `repairable`
decides between `revision_requested` and `rejected`. Codes are stable strings
and appear in the M7 audit event.

## 6. Guarantees the other components may rely on

1. A `scene_update` only ever contains registry operations whose object references exist in the simulated scene after the preceding operations.
2. A `scene_update` never removes or overwrites a base-lesson object.
3. Every numeral in narration or labels was computed by the solver for this request.
4. Every `source_ref` is in the approved set for the lesson; quarantined passages are never retrievable.
5. The same `request_id` yields at most two verification records, and every record carries `verifier_version`, `planner_id`, `config_version` and the reason codes.
6. If the audit sink is unavailable the HTTP service refuses to decide (503).

## 7. What this contract does not promise

Pedagogical quality (M5), rendering fidelity (M8), and correctness of
*presentation choices* (which object to highlight) are outside the verifier.
The injection scanner is heuristic; the canary check and narration discipline
are the backstops. See `docs/verification/README.md` for measured limits.
