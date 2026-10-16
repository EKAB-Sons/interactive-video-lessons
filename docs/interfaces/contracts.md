# Interface contracts

Planner and verifier boundaries are defined with JSON Schema
(Draft 2020-12) plus two registries. The normative statement of what a plan
must satisfy is `spec/acceptance-contract.md`; this page is the index.

| Contract | File | Notes |
|---|---|---|
| Context packet | `contracts/schemas/context_packet.schema.json` | request/session/lesson ids, `scene_version`, question, selections, approved `source_refs`, `deadline_ms` |
| Scene graph | `contracts/schemas/scene_graph.schema.json` | object ids `namespace.name`, kinds, origin `base`/`branch` |
| Claim | `contracts/schemas/claim.schema.json` | seven typed mathematical statements with per-type required fields |
| Adaptation plan | `contracts/schemas/adaptation_plan.schema.json` | `oneOf` proposal / clarification / failure; validated per declared kind for precise error paths |
| Lesson plan | `contracts/schemas/lesson_plan.schema.json` | base lesson: nodes with claims, operations, practice items bound to claims |
| Verification result | `contracts/schemas/verification_result.schema.json` | six statuses, issues, checked claims, `scene_update` (rendered=false), fallback |
| Revision instruction | `contracts/schemas/revision_instruction.schema.json` | failed checks with computed values plus the constraints the retry must respect |
| Operations registry | `contracts/operations.json` (`ops-v1`) | argument types, object references by kind, created/removed objects, `fact_bearing` flag |
| Topics registry | `contracts/topics.json` (`topics-v1`) | bounded topic set: allowed operations, claim types, functions, variables |

All schemas are served by the verification service at `GET /contracts/{name}`.

Allowed operations (`ops-v1`): `highlight`, `unhighlight`, `set_narration`,
`show_secant_sequence`, `draw_tangent`, `draw_secant`, `plot_function`,
`annotate_value`, `add_label`, `remove_object`, `zoom`. Fact-bearing operations
must reference a verified claim of the right type; narration states numbers only
through `{{claim:id}}` placeholders.
