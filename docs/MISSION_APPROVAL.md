# Mission Approval Continuity

Mission Approval Continuity makes policy-blocked mission work durable and operator-actionable across the Console, kernel, and CLI.

## Guarantees

- Policy-blocked tasks update the associated mission to `blocked` instead of leaving stale mission state.
- Approval-required outcomes record `approval_required=true` in durable mission outcome state.
- A mission-scoped approval operation can approve one or all blocked tasks that belong to that mission graph.
- Approval requeues the original task instead of creating a duplicate task.
- Approved tasks are marked `approved=true` and `approved_by=operator`, then re-enter the normal dispatcher and policy path.
- Successful nodes remain untouched during mission approval.

## Interfaces

HTTP:

`POST /api/missions/{mission_id}/approve`

Optional body:

`{"task_ids": ["..."]}`

CLI:

`python -m oth.cli mission approve <mission_id>`

`python -m oth.cli mission approve <mission_id> --task-id <task_id>`

## Safety boundary

Approval does not bypass the dispatcher. It only records explicit operator authorization and queues the task. The task is still routed through normal policy, lane selection, worker execution, verification, evaluation, and mission reconciliation.

## Verification

- Focused mission bridge tests: PASS.
- Full OTH test suite: PASS, exit code 0.
- Live Console approval validation: PASS against the real `console.db` and `oth.db`.
  - Disposable external publish task was policy-blocked.
  - Mission became `blocked` with `approval_required=true`.
  - `POST /api/missions/{mission_id}/approve` returned the task as approved.
  - Task and mission transitioned to `queued`.
  - `approved_by=operator` was persisted.
  - Validation records were removed after the check.
