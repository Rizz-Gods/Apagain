# Mission Deadline and Watchdog

Mission Deadline and Watchdog adds durable time awareness to OTH missions without introducing silent auto-cancellation or automatic task mutation.

## Deadline model

Every mission now has:

- `deadline_at` — optional timezone-aware ISO-8601 timestamp.
- `watchdog_status` — `ok` or `overdue`.
- `watchdog_checked_at` — last watchdog observation time.

Existing `console.db` files are migrated in place when `MissionStateStore` starts.

## Operator interfaces

CLI:

`python -m oth.cli mission deadline <mission_id> --at 2026-10-06T12:00:00+05:30`

Clear a deadline:

`python -m oth.cli mission deadline <mission_id> --clear`

HTTP:

`POST /api/missions/{mission_id}/deadline`

Set:

`{"deadline_at":"2026-10-06T12:00:00+05:30"}`

Clear:

`{"deadline_at":null}`

The unified mission control response also exposes:

- deadline timestamp,
- watchdog status,
- last watchdog check,
- overdue duration in seconds.

## Watchdog behavior

The daemon invokes the mission watchdog on every runner cycle.

When an active mission passes its deadline:

- mission execution status is left unchanged,
- `watchdog_status` becomes `overdue`,
- `latest_outcome.deadline_exceeded` records the deadline,
- `mission.deadline_exceeded` is added to the durable timeline.

The watchdog does not cancel, retry, fail, or terminate tasks.

## Safety boundary

A deadline is an operator-visible timing signal, not a kill switch.

This keeps deadline handling orthogonal to the established approval, retry, cancellation, and recovery mechanisms.

## Verification

- Focused deadline suite: PASS (3/3).
- Full OTH pytest suite: PASS (100%, exit code 0, runtime ~22.2s).
- Real Console deadline API: PASS.
- Disposable blocked mission received a past deadline through the live HTTP API.
- Live control snapshot reported `watchdog_status=overdue` and the overdue duration.
- Mission timeline contained `mission.deadline_set` and `mission.deadline_exceeded`.
- Disposable mission/task/timeline records were removed after validation.
