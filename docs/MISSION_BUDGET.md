# Mission Resource Guardrails

Mission Resource Guardrails place durable execution-volume limits on every mission.

## Guardrails

Each mission has:
- `max_tasks`: maximum reachable task nodes in its mission graph.
- `max_retries`: maximum mission-wide retry schedules across those tasks.

Defaults for new missions are:
- 256 task nodes.
- 8 retries.

The deadline/watchdog remains the wall-clock guardrail. These limits protect against runaway task spawning and repeated recovery loops.

## Enforcement

### Task creation

When a task carries a mission ID, OTH checks the mission task graph before insertion.

When `max_tasks` is already exhausted:
- the task is created as `blocked`
- a durable `task.budget_exhausted` event is written
- mission timeline records `mission.budget_blocked_task`
- mission state becomes budget-aware
- a critical `mission.budget_exhausted` attention item is created

The graph is preserved rather than silently dropping the requested child.

### Retry scheduling

Before a failed task is requeued, OTH checks the mission retry budget.

When `max_retries` is exhausted:
- the task remains `failed`
- no `task.retry_scheduled` event is created
- budget state becomes `retries_exhausted`
- a critical budget attention item is exposed

Tasks without a mission retain the existing per-task retry behavior.

## Operator controls

CLI:

`python -m oth.cli mission budget <mission_id>`

With no limits, the command reports the current budget.

Set either or both limits:

`python -m oth.cli mission budget <mission_id> --max-tasks 100 --max-retries 4`

HTTP:

`GET /api/missions/{mission_id}/budget`

`POST /api/missions/{mission_id}/budget`

Example body:

`{"max_tasks":100,"max_retries":4}`

The mutation is recorded in the operator audit ledger as `mission.budget.policy_set`.

Mission Control exposes the current task/retry counts, limits, remaining capacity, and budget status.

## Safety behavior

Changing a budget never automatically resumes or dispatches blocked work.

Increasing a limit only restores future capacity. Existing blocked tasks remain blocked until an existing approval/resume path is used where applicable.

The guardrail itself has no external side effects.

