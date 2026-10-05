# Mission Integrity Monitoring

Mission Integrity Monitoring continuously checks durable mission invariants without automatically repairing state.

## Invariants checked

For each mission, the monitor validates:
- mission status matches the reachable task graph aggregate
- terminal missions have no active queued/running/blocked tasks
- terminal missions have `completed_at`
- non-terminal missions do not have `completed_at`
- all root tasks remain reachable
- latest mission task remains in the graph
- stored budget status matches the computed budget
- mission policy revision matches the pinned policy revision
- mission policy hash matches the pinned policy hash
- operator audit hash chain remains valid

## Durable checks

Results are stored in `mission_integrity_checks`.

Each check records:
- status: `healthy` or `violated`
- timestamp
- structured violations
- fingerprint

A repeated identical violation fingerprint does not generate another mission attention event.

When a new violation fingerprint appears:
- mission timeline receives `mission.integrity_violation`
- the attention inbox receives a critical integrity alert

The monitor does not mutate task or mission state to repair the problem.

## Runtime integration

The OTH runner calls the integrity monitor each daemon cycle after reconciliation and watchdog evaluation.

This makes integrity checking part of normal long-running operation rather than a manual diagnostic.

## Interfaces

CLI:

`python -m oth.cli mission integrity <mission_id> [--history N]`

HTTP:

`GET /api/missions/{mission_id}/integrity`

Mission Control exposes the current integrity status.

Integrity history is available through the same API and through the underlying durable store.

## Forensics

Integrity checks are included in mission control and mission timeline evidence.

A violation therefore becomes visible across:
- operator attention
- mission timeline
- forensic replay
- current mission control state

