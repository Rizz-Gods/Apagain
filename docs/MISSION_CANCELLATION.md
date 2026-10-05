# Mission Cancellation and Graceful Intervention

Mission Cancellation adds a truthful operator cancellation boundary to the OTH mission control plane.

## Semantics

HTTP:

POST /api/missions/{mission_id}/control

with:

{"action":"cancel"}

Optional fields:

- task_ids — restrict cancellation to selected mission nodes.
- reason — durable operator reason, defaulting to operator_cancel.

CLI:

python -m oth.cli mission cancel <mission_id>

Optional task restriction:

python -m oth.cli mission cancel <mission_id> --task-id <task_id>

### Queued and blocked tasks

Queued or approval-blocked tasks are cancelled immediately.

The task status becomes cancelled, a durable task.cancelled event is recorded, and the mission timeline records mission.task_cancelled.

### Running tasks

Running work is not force-terminated.

The control plane stores _cancel_requested=true, records task.cancel_requested, and exposes the operation as a graceful cancellation request. The mission remains running until the synchronous worker returns.

This avoids claiming that external work stopped when the current worker architecture has no safe preemption primitive.

### Terminal aggregation

Mission aggregation now recognizes cancelled as terminal.

A graph composed only of succeeded and cancelled nodes becomes cancelled when any node is cancelled, and remains succeeded only when every node succeeds.

Active states still take precedence, followed by failed and blocked states.

## Safety boundary

Cancellation is an operator control, not a worker kill switch.

No process is terminated and no external platform request is forcibly interrupted by this subsystem.

## Verification status

Focused cancellation coverage was added in tests/test_mission_cancellation.py for queued task cancellation, blocked task cancellation, and graceful cancellation requests for running tasks.

Local full-suite and live Console validation remain pending until the Windows runtime reconnects.
