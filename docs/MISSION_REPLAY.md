# Mission Forensics and Replay

Mission Forensics and Replay reconstructs one mission as a read-only chronological evidence stream from the durable mission timeline, underlying task events, and operator audit ledger.

## Replay model

The replay combines mission timeline events, task database events for reachable mission tasks, and operator audit entries.
Each replay record preserves its source, task identity, event kind, status/result, payload, and timestamp, then receives a deterministic sequence number.
Replay ordering is timestamp-first, then mission evidence before audit evidence for equal timestamps, then durable row ID.

## Integrity and summary

Replay exposes the mission audit-chain verification result, current mission state, reachable task graph, evidence counts, first and last observed timestamps, duration when timestamps are parseable, and source/event-kind summaries.
Replay is bounded by a caller-provided limit with a safe maximum.

## Interfaces

CLI: python -m oth.cli mission replay <mission_id> --limit N

HTTP: GET /api/missions/{mission_id}/replay

Mission Control loads replay through this dedicated read-only endpoint so the normal control snapshot is not inflated by repeated reconstruction work.

## Safety boundary

Mission replay is observational only. It never creates or mutates tasks and never executes operator actions.
