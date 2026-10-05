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
- `cancel` — delegates to `OTHKernel.cancel_mission()`; queued/blocked tasks cancel immediately while running tasks receive a graceful cancellation request.
- `refresh` — reconciles the mission and reloads the control snapshot.

Optional fields:

`task_ids`: restrict approval, resume, or cancellation to selected mission nodes.

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
- Cancellation is graceful: it never force-terminates a running worker.
- Running-task cancellation is represented as a durable request until the synchronous worker returns.

## Verification state

- Focused Mission Control regression tests: PASS (2/2).
- Full OTH pytest suite: PASS (100%, exit code 0, runtime ~40.6s).
- Real Console `GET /api/missions/{mission_id}/control`: PASS.
- Real Console `POST /api/missions/{mission_id}/control` approval: PASS.
- A blocked disposable mission exposed the exact approval-eligible task.
- Approval requeued that exact task and persisted `approved_by=operator`.
- The returned control snapshot reflected updated mission, graph, timeline, and action availability.
- Disposable mission/task/timeline records were deleted after validation.
- Runtime duplicate-process cleanup was completed; the authoritative PID-file processes remain.

Detailed cancellation contract: docs/MISSION_CANCELLATION.md
