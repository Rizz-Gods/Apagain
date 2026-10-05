Mission Progress and ETA adds a truthful read-only execution view on top of the existing mission graph, timeline, deadline, and escalation infrastructure.

## Progress model

For a mission graph:

- completed = succeeded + failed + cancelled
- active = queued + running + blocked
- percent = completed / total
- elapsed time = current time - mission creation time

The control snapshot exposes these values under progress.

## ETA model

ETA is intentionally conservative.

For terminal tasks, OTH observes each task's wall-clock cycle from task creation to its terminal update. The progress layer computes:

- average_cycle_seconds
- throughput_per_minute
- eta_seconds = active task count × observed average cycle

ETA is exposed only when terminal-task history exists. Otherwise eta_confidence is insufficient_history and ETA remains null.

This is a planning estimate, not an execution promise.

## Operator interfaces

CLI:

python -m oth.cli mission progress <mission_id>

HTTP:

GET /api/missions/{mission_id}/progress

The unified mission control response also exposes the progress object.

The Console UI renders:

- completion percentage,
- terminal/total task count,
- progress bar,
- conservative ETA when observed history exists.

## Safety boundary

Progress never changes task state.

It does not:

- dispatch work,
- retry work,
- cancel work,
- approve work,
- mutate deadlines,
- mutate escalation thresholds.

It reads the existing mission graph and durable timestamps only.

## Verification

- Focused progress suite: PASS (2/2).
- Partial completion and observed ETA: PASS.
- No-history ETA suppression: PASS.
- Full suite and live Console validation recorded in the mission handoff.
