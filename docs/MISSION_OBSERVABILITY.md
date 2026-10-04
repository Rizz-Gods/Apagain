# Mission Observability and Execution Timeline

Mission Observability provides one operator-facing timeline for each mission by combining durable mission lifecycle events with the underlying task-event stream.

## What the timeline shows

Mission-level events include creation, root-task attachment, task-state updates, reconciliation, resume actions, and approval grants.

Task-level events are pulled from the authoritative `oth.db` event stream for every task reachable from the mission graph. Each task event keeps its original task ID and payload and is marked with `source=task_event`.

## Interfaces

HTTP:

`GET /api/missions/{mission_id}/timeline`

CLI:

`python -m oth.cli mission timeline <mission_id>`

Optional CLI limit:

`python -m oth.cli mission timeline <mission_id> --limit 100`

## Durability model

Mission lifecycle events are stored in `data/console.db` in the `mission_timeline` table. Execution events remain authoritative in `data/oth.db`; the timeline correlates them by the mission's reachable task graph rather than copying or mutating task history.

This keeps the operator timeline durable across Console restarts while preserving the task database as the source of truth for execution details.

## Safety and bounds

Timeline reads are bounded to 500 combined events. Graph traversal remains bounded by the existing mission graph limit. No execution, approval, retry, or worker behavior is changed by reading the timeline.

## Verification

- Mission bridge timeline test: PASS.
- Full OTH test suite: PASS, exit code 0.
- Live Console timeline validation: PASS against the real `console.db` and `oth.db`.
  - Real disposable mission executed successfully.
  - Timeline returned 9 correlated events.
  - Mission lifecycle events were present.
  - Underlying task events were present with the exact task ID.
  - Disposable mission/task/timeline records were removed afterward.
