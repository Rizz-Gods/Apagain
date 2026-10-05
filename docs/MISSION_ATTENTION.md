Mission Attention Inbox turns important mission signals into durable operator-facing alerts.

## Attention model

Attention records are stored in the persistent Console database.

Each item contains:

- mission and optional task identity,
- severity: warning or critical,
- source event kind,
- operator-readable title/detail,
- open or acknowledged status,
- creation and acknowledgment timestamps,
- acknowledgment actor.

Attention is generated from meaningful durable mission timeline events such as:

- approaching deadline,
- critical deadline,
- deadline exceeded,
- approval required,
- task escalation,
- graceful cancellation request,
- failed mission task,
- blocked mission task.

Attention generation is idempotent per timeline event.

## Operator interfaces

CLI:

python -m oth.cli attention list

python -m oth.cli attention list --mission-id <mission_id>

python -m oth.cli attention list --all

python -m oth.cli attention ack <attention_id>

HTTP:

GET /api/attention

GET /api/missions/{mission_id}/attention

POST /api/attention/{attention_id}/acknowledge

The unified mission control response exposes:

- open attention items,
- open attention count.

The Console UI renders open mission attention items with an explicit Acknowledge action.

## Safety boundary

Attention does not execute work.

Acknowledging an item only changes the attention record's operator state. It does not:

- approve a task,
- resume a task,
- cancel a task,
- change deadlines,
- change escalation thresholds,
- dispatch workers,
- trigger external side effects.

## Verification

- Focused attention suite: PASS (3/3).
- Full OTH pytest suite: PASS (100%, exit code 0, runtime 43.77s).
- Live Console alert creation: PASS.
- Live global attention inbox: PASS.
- Live mission-control attention: PASS.
- Live operator acknowledgment: PASS.
- Acknowledged alert disappeared from both open queues.
- Disposable validation mission/timeline/attention rows were removed.
