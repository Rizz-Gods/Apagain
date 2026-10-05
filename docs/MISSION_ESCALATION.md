Mission SLA Escalation adds durable timing escalation on top of the existing Mission Deadline and Watchdog subsystem.

## Escalation model

Every mission now carries:

- escalation_level — normal, warning, critical, or overdue.
- escalation_warning_seconds — default 900 seconds before the deadline.
- escalation_critical_seconds — default 300 seconds before the deadline.
- escalation_checked_at — last escalation evaluation time.

Existing console.db files are migrated in place when MissionStateStore starts.

## State machine

For active missions with a deadline:

normal -> warning -> critical -> overdue

The transition is derived from the current time and the mission's configured thresholds.

Escalation evaluation is idempotent. Repeated watchdog cycles update check timestamps and durable outcome state but emit timeline events only when the escalation level changes.

## Operator interfaces

CLI:

python -m oth.cli mission escalation <mission_id> --warning-before 900

python -m oth.cli mission escalation <mission_id> --critical-before 300

Reset both thresholds to defaults:

python -m oth.cli mission escalation <mission_id> --reset

HTTP:

POST /api/missions/{mission_id}/escalation

Example:

{"warning_before_seconds":900,"critical_before_seconds":300}

Reset:

{"reset":true}

The unified mission control response now exposes:

- current escalation level,
- seconds to deadline,
- warning threshold,
- critical threshold,
- last escalation check.

The Console UI surfaces the current escalation level beside the mission deadline/status.

## Watchdog behavior

The daemon continues to invoke the existing mission watchdog every runner cycle.

When an active mission enters a new escalation state:

- mission execution status is unchanged,
- no task is cancelled,
- no task is failed,
- no task is retried,
- no external side effect is triggered,
- a durable mission timeline event records the transition.

Timeline event kinds include:

- mission.escalation_policy_set
- mission.escalation_warning
- mission.escalation_critical
- mission.deadline_exceeded
- mission.escalation_cleared

The latest mission outcome also stores deadline_escalation with the level, remaining time, and thresholds.

## Safety boundary

SLA escalation is an operator-visible signal, not an execution policy.

Approval, retry, cancellation, recovery, and deadline mechanisms remain separate control planes. Escalation never silently mutates task execution state.

## Verification

- Focused mission deadline/escalation suite: PASS (5/5).
- Policy ordering validation: PASS.
- Escalation transition persistence: PASS.
- Repeated overdue evaluation remains timeline-idempotent: PASS.
- Unified control snapshot exposes escalation state and thresholds: PASS.
