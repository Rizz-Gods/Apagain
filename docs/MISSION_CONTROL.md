# Mission Control Plane

Mission Control Plane is the unified operator surface for a durable OTH mission. It composes the mission record, reachable task graph, execution timeline, and policy-aware operator actions without duplicating execution logic.

## Unified read surface

HTTP:

`GET /api/missions/{mission_id}/control`

The response contains:

- `mission`: durable mission state.
- `graph`: reachable task nodes, edges, and status counts.
- `timeline`: correlated mission and task events.
- `actions`: currently available operator actions and their eligible task IDs.

The read path reconciles mission state from the authoritative task graph before returning the snapshot.

## Unified action surface

HTTP:

`POST /api/missions/{mission_id}/control`

Supported actions:

- `approve` — delegates to `OTHKernel.approve_mission()`.
- `resume` — delegates to `OTHKernel.resume_mission()`; external and financial policy gates remain enforced.
- `refresh` — reconciles the mission and reloads the control snapshot.

Optional fields:

`task_ids`: restrict approval or resume to selected mission nodes.

`approve_external`: explicitly authorize external/financial failed-task resume when the existing kernel policy requires it.

The older `/approve` and `/resume` endpoints remain available for compatibility.

## Console

The browser console now presents a Mission Command Center containing:

- mission goal and status,
- graph counters,
- available operator actions,
- recent correlated timeline events,
- explicit follow-up for failed tasks that remain approval-gated.

The UI does not execute workers directly. All execution still flows through the existing kernel approval and resume controls.

## Safety boundary

The control plane is an orchestration/read surface, not a second execution engine.

- Reads reconcile state but do not execute worker tasks.
- Approval is explicit.
- Resume preserves the existing external/financial risk gate.
- No stop/cancel semantics were invented before the kernel has a durable cancellation model.

## Verification state

Focused regression coverage was added in `tests/test_mission_control.py` for:

- failed missions exposing a resume action,
- blocked missions exposing an approval action,
- graph/timeline/action composition.

The local Windows runtime could not be reconnected during this checkpoint, so live Console HTTP validation and a full pytest run remain pending.
