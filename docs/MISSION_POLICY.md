# Mission Policy Versioning and Governance

Mission Policy Versioning pins governance rules to each mission and makes policy-sensitive execution attributable to an immutable revision.

## Governance revision

Each mission carries:
- `policy_revision`
- `policy_hash`
- mission-scoped approval requirements
- cancellation mode

Durable revisions live in `mission_policy_revisions`.

Each revision stores:
- revision number
- complete policy document
- canonical SHA-256 hash
- actor
- reason
- creation time

The policy document covers:
- approval: external and financial approval requirements
- deadline
- escalation thresholds
- execution budget
- cancellation semantics

A revision is never rewritten. Mutations create a new revision.

## Revision triggers

A new mission receives revision 1.

The following policy mutations create a new revision:
- deadline set/clear
- escalation thresholds changed
- task/retry budget changed
- approval policy changed
- cancellation mode change

Existing missions are backfilled into revision 1 during migration.

## Enforcement

Kernel policy evaluation for mission tasks uses the mission's pinned approval policy rather than the live global policy file.

Every policy-sensitive dispatch emits `task.policy_evaluated` with:
- decision
- reason
- risk
- mission ID
- active policy revision
- active policy hash

Changing a mission policy affects subsequent decisions only. Previously recorded decisions retain their original revision/hash.

## Operator evidence

Existing mission audit entries automatically carry the active policy revision and hash.

Policy changes create:
- immutable policy revision
- `mission.policy_revision_created` timeline evidence
- specific operator audit for the mutation

This preserves the existing audit contract while making every operator decision attributable to a governance state.

## Interfaces

CLI:

`python -m oth.cli mission policy <mission_id>`

Inspect the current revision without mutation.

Change approval requirements:

`python -m oth.cli mission policy <mission_id> --external-approval not-required`

The CLI also supports `--financial-approval required|not-required` and `--reason`.

HTTP:

`GET /api/missions/{mission_id}/policy`

`POST /api/missions/{mission_id}/policy`

The unified mission control surface exposes the current policy revision and hash.

## Forensics

Mission replay exposes:
- current policy
- policy revision history
- policy revision count
- policy entries in the chronological replay

This means a long-running mission can reconstruct not only what happened, but which governance revision was active when each decision was made.

