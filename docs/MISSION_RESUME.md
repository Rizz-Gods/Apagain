# Mission Resume and Retry Control

Mission Resume and Retry Control provides an explicit operator action for recovering failed mission nodes without restarting successful work.

## Guarantees

- Only failed tasks in the selected mission graph are eligible for resume.
- Successful tasks remain untouched.
- Resumed tasks keep their original task ID and graph position.
- Lane failure exclusions are cleared so the next execution cycle can select the available recovery lane again.
- Retry attempts are reset for the new operator recovery cycle and `_resume_count` is incremented for auditability.
- Mission status is reconciled immediately after requeueing.

## Risk boundary

Resume does not bypass OTH policy.

- Safe and local-write failed tasks can be requeued directly.
- External and financial failed tasks require explicit `approve_external=true` on the resume operation.
- When explicitly approved, the task payload is marked `approved=true` and `approved_by=operator` so the normal policy gate sees the operator approval during dispatch.
- Blocked approval-required tasks continue to use the existing task approval path; resume does not silently convert them into execution permission.

## Interfaces

CLI:

`python -m oth.cli mission status <mission_id>`

`python -m oth.cli mission resume <mission_id>`

`python -m oth.cli mission resume <mission_id> --task-id <task_id> --approve-external`

HTTP:

`POST /api/missions/{mission_id}/resume`

Body fields:

- `task_ids` — optional list of failed task IDs. Omit it to resume every eligible failed task in the mission graph.
- `approve_external` — optional boolean. Defaults to false.

## Audit

Every requeued task gets a durable `mission.resume_queued` event containing the mission ID, operator reason, and whether the resume included explicit external approval.

## Verification

- Focused mission bridge tests: PASS.
- Full OTH test suite: PASS, exit code 0.
- Live Console HTTP validation: PASS against the real `console.db` and `oth.db`.
  - Disposable failed mission created.
  - `POST /api/missions/{mission_id}/resume` returned `queued` with the exact failed task ID.
  - Mission transitioned to `queued`.
  - Task transitioned to `queued`.
  - Validation records were removed after the check.

## Recovery model

Mission state remains truthful and resumable without rewinding successful graph work. OTH still executes the resumed task through the normal dispatcher, worker lanes, verification, evaluation, and policy gates.
