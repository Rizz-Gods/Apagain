# Mission Operator Audit Ledger

The Mission Operator Audit Ledger records durable decisions and operator mutations separately from the execution timeline.

## Storage

Audit entries live in `data/console.db` in the `mission_audit` table.

Each entry stores:
- mission and optional task identity
- actor
- action
- result
- structured payload
- timestamp
- previous hash
- entry hash

Entries are append-only through the OTH application surface. Each hash is computed from the canonical entry contents and the previous ledger hash, creating a tamper-evident global chain.

## Covered mutations

The current mission control surface records:
- mission creation
- deadline set/clear
- SLA escalation policy changes
- task approval
- mission resume/retry
- mission cancellation
- attention acknowledgement

Execution state changes remain in the mission timeline; the audit ledger captures the decision that caused or acknowledged an operator-facing state transition.

## Verification

The MissionStateStore exposes:
- `audit_for_mission(mission_id)`
- `list_audit(limit, mission_id=None)`
- `verify_audit_chain(mission_id=None)`

Verification recomputes each entry hash and checks the expected previous hash. A mismatch returns the first broken ledger entry.

## Interfaces

CLI:

`python -m oth.cli mission audit <mission_id>`

Add `--limit N` to bound the result and `--verify` to include chain verification.

HTTP:

`GET /api/missions/{mission_id}/audit`

The response contains the audit items and chain integrity result.

The unified mission control endpoint also exposes:
- `audit`
- `audit_integrity`

## Safety boundary

Reading or verifying the audit ledger never executes mission work.

Acknowledging an attention item remains an acknowledgement only; it does not approve, resume, cancel, change deadlines, or dispatch tasks.

No application endpoint deletes or rewrites audit entries. Direct database tampering is detectable through hash verification.
