# Interface contracts

The stub uses explicit Python validation, not JSON Schema. Structural validation checks required fields/types; scene-reference and operation validation are separate. A valid structure is not proof of educational correctness.

| Contract | Required fields / statuses |
|---|---|
| Lesson request | `request_id`, `session_id`, `lesson_id`, `node_id`, `scene_version` |
| Interruption context | above plus question, selected objects, source refs |
| Adaptation proposal | kind, IDs/versions, planner/config, refs, operations, return anchor |
| Clarification/failure | kind, request ID, status, reason |
| Verification result | request ID, accepted/rejected, reason code |
| Scene update | base version, allowlisted operations, `rendered=false` |
| Session checkpoint | session/lesson/node IDs, branch, anchor |
| Monitoring event | correlation ID, stage, status, versions, outcome |

Allowed operations: `highlight`, `show_secant_sequence`, `set_narration`. References must exist in the active scene.
