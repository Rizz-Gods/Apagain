# Mission Recovery Reconciliation

Mission Recovery Reconciliation keeps durable mission state aligned with the authoritative task graph after worker or daemon interruptions.

## Guarantees

- Stale running tasks are still reclaimed by the existing task lease logic.
- Mission records are reconciled from root tasks and all reachable descendants.
- A lease-expired descendant moves its mission to failed instead of leaving stale running state in Console memory.
- Console mission reads reconcile state before returning results.
- The daemon runner reconciles missions on every execution cycle after stale-task reclamation.
- Latest task identity is recovered from the graph when a mission is reconciled.

## Recovery boundary

Automatic recovery is deliberately conservative. OTH does not blindly re-execute failed work because external or non-idempotent actions may already have occurred. Reconciliation establishes truthful state first; explicit retry/resume policy can build on top of that state later.

## Verification

- Focused mission recovery tests: PASS.
- Full OTH suite: PASS after integration.
- Recovery unit path forces a task lease to expire, then reconciles the mission to failed with the recovered task as latest task.

## Runtime path

Daemon loop -> reclaim stale tasks -> reconcile MissionStateStore -> scheduler -> execute queued work.

Console mission API -> reconcile MissionStateStore -> return mission graph.
