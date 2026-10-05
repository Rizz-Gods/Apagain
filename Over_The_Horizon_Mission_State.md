# Over The Horizon — Mission State

## Current subsystem: Mission Attention Inbox

Status: IMPLEMENTED — FOCUSED-TESTED; FULL AND LIVE VALIDATION IN PROGRESS

Previous subsystem: Mission Progress and ETA — complete and live-validated

### Completed
- Native local engineering worker: `ollama-engineer`
  - Direct Ollama execution
  - Model routing through the OTH ModelRouter
  - Controlled repository tools: list/read/search/write/replace/run/git/status/diff/finish
  - Dynamic WSL Ollama endpoint discovery
  - Safe command allowlist
  - Explicit finish requirement
  - Failed tool calls make the worker fail
  - Verification runs after the agent loop
- Secondary engineering adapter: `opencode-engineer`
  - Retained as resilience lane
  - Uses the same implementation-evidence contract
- Honest fallback: `engineering-audit-fallback`
  - Never claims code execution when no provider is available
- Engineering evidence layer:
  - `oth/core/engineering_evidence.py`
  - Detects whether a mission expects mutation
  - Captures content-level workspace fingerprints
  - Handles dirty working trees correctly
  - Supports non-Git repositories with deterministic tree fingerprints
- Kernel-level guard:
  - `oth/core/kernel.py`
  - Independently rejects an engineering worker result that claims success without required implementation evidence
  - A failed lane is recorded and the next eligible engineering lane can recover the task
- Persistent engineering scorecard:
  - `Database.engineering_scorecard()`
  - CLI: `python -m oth.cli engineering scorecard`
  - Reports runs, successes, failures, average quality, average lane, last run
- Tests added/expanded:
  - `tests/test_engineering_evidence.py`
  - `tests/test_engineering_kernel_guard.py`
  - `tests/test_engineering_worker.py`
  - `tests/test_ollama_engineer.py`
  - `tests/test_pilot_routing.py`
- Pilot routing hardening:
  - Explicit technical implementation intent now gets a deterministic `engineering/execute` route before broad media/content matches.
  - Research-only technical questions remain out of engineering execution.
- Scorecard metadata persistence:
  - Engineering evaluations persist provider, model, tier, complexity, implementation-change, verification, and attempt metadata.
  - `engineering scorecard` exposes latest outcome metadata per worker.
- Contract documentation:
  - `docs/ENGINEERING_EXECUTION_CONTRACT.md`
- Mission Continuity subsystem:
  - `oth/core/mission_state.py`
  - Durable mission records in `data/console.db`
  - Console-to-kernel mission identity propagation
  - Root-task status aggregation and terminal outcome persistence
  - Structured mission state injected into model context
  - API: `GET /api/conversations/{conversation_id}/mission`
  - Documentation: `docs/MISSION_CONTINUITY.md`
- Mission Continuity tests:
  - `tests/test_mission_continuity.py`
  - `tests/test_mission_kernel_bridge.py`
- Mission Graph Continuity subsystem:
  - Child handoffs inherit mission and conversation identity.
  - Event-triggered child tasks inherit the same mission identity.
  - Mission status aggregates roots and all reachable descendant tasks.
  - Mission state is refreshed after child spawning so queued descendants cannot be missed.
  - Console mission API now exposes graph nodes, edges, and status counts.
  - Documentation: `docs/MISSION_GRAPH_CONTINUITY.md`
- Mission Recovery Reconciliation subsystem:
  - Durable mission rows reconcile from the authoritative task graph.
  - Daemon runner reconciles missions immediately after stale-task reclamation.
  - Console mission reads reconcile before returning state.
  - Stale-task recovery preserves truthful failed/running/queued mission state.
  - Automatic re-execution is intentionally not performed; reconciliation is the safe recovery boundary.
  - Documentation: `docs/MISSION_RECOVERY.md`
- Mission Resume and Retry Control subsystem:
  - Failed mission nodes can be explicitly resumed without restarting successful nodes.
  - Original task IDs and graph positions are preserved.
  - Lane failure exclusions and retry counters reset for a new recovery cycle.
  - External/financial failed tasks remain approval-gated unless `approve_external=true` is explicitly supplied.
  - Every resumed task records a durable `mission.resume_queued` audit event.
  - Console API: `POST /api/missions/{mission_id}/resume`
  - CLI: `python -m oth.cli mission status|resume ...`
  - Documentation: `docs/MISSION_RESUME.md`
- Mission Approval Continuity subsystem:
  - Policy-blocked tasks now update their mission to `blocked` with durable approval metadata.
  - Mission-scoped approval can requeue one or all blocked tasks without duplicating graph nodes.
  - Approval persists `approved=true` and `approved_by=operator` and re-enters the normal dispatcher.
  - Console API: `POST /api/missions/{mission_id}/approve`
  - CLI: `python -m oth.cli mission approve ...`
  - Documentation: `docs/MISSION_APPROVAL.md`
- Mission Observability and Execution Timeline subsystem:
  - Durable mission lifecycle events are stored in `data/console.db`.
  - Underlying `oth.db` task events are correlated by the reachable mission task graph.
  - Timeline entries preserve task IDs and source (`mission` vs `task_event`).
  - Console API: `GET /api/missions/{mission_id}/timeline`
  - CLI: `python -m oth.cli mission timeline ...`
  - Timeline reads are bounded to 500 events and do not execute actions.
  - Documentation: `docs/MISSION_OBSERVABILITY.md`
- Mission Control Plane / Operator Command Center subsystem:
  - Unified HTTP read surface: `GET /api/missions/{mission_id}/control`.
  - Unified HTTP action surface: `POST /api/missions/{mission_id}/control`.
  - Control snapshot composes durable mission state, reachable graph, correlated timeline, and available operator actions.
  - Approve/resume actions delegate to the existing kernel safety gates; no second execution path was introduced.
  - Console UI now exposes mission status, graph counters, recent timeline, approval, and resume controls.
  - Documentation: `docs/MISSION_CONTROL.md`.
- Mission Cancellation and Graceful Intervention subsystem:
  - Queued and blocked mission tasks can be cancelled immediately.
  - Running tasks receive a durable graceful cancellation request; the current synchronous worker is never force-terminated.
  - Mission aggregation recognizes `cancelled` as terminal.
  - Unified Mission Control now exposes a `cancel` action.
  - CLI: `python -m oth.cli mission cancel ...`.
  - Documentation: `docs/MISSION_CANCELLATION.md`.

### Verification achieved
- Focused engineering tests: PASS
- Full OTH test suite: PASS (exit code 0)
- Live OTH Console mission: PASS
  - Console-originated mission routed to `engineering/execute`
  - Root task: `7d236c5d-6a5d-42e9-a569-e111d5686bd8`
  - Winning worker: `ollama-engineer`
  - Model: `ollama/qwen2.5-coder:1.5b-instruct`
  - Provider: `ollama-native`
  - Complexity: `0.259`
  - Tool steps: `3`
  - Implementation change observed: `true`
  - Verification: full pytest suite passed
  - Evaluation quality: `1.0`
- Live scorecard exposes the model/worker outcome metadata above.
- Live Mission Continuity validation: PASS
  - Console conversation: `7740ba8b-1d11-4aef-b0ae-1b89936d99bf`
  - Mission: `138c6012-bca4-47f6-878b-8b37e66f3646`
  - Root task: `cbd5affa-caef-4f51-a3b4-36010ce228b6`
  - Mission transitioned `queued -> succeeded`
  - Winning worker: `ollama-engineer`
  - Model: `ollama/qwen2.5-coder:1.5b-instruct`
  - Implementation evidence observed: `true`
  - Full pytest verification: passed
  - Mission quality: `1.0`
- Live Mission Graph Continuity validation: PASS
  - Real OTH `data/oth.db` and `data/console.db` exercised.
  - Root succeeded and spawned a queued child.
  - Mission remained `queued` until the child completed.
  - Graph reported 2 tasks, 1 queued descendant, and 1 edge.
  - Child inherited mission/conversation identity.
  - Child then succeeded and mission closed `succeeded` with child as latest task.
- Mission Recovery Reconciliation verification: PASS
  - Full OTH test suite passed with exit code 0.
  - Real OTH databases exercised in a transient lease-expiry validation.
  - A running task was reclaimed as stale.
  - Mission reconciliation changed the mission to `failed` and recovered the stale task as latest task.
  - Validation mission/task rows were removed after the check.
- Mission Resume and Retry Control verification: PASS
  - Full OTH test suite passed with exit code 0.
  - Safe failed-node resume test passed.
  - External-risk resume remained blocked without explicit approval and queued only after explicit approval.
  - Live Console HTTP endpoint validation passed against the real OTH databases.
  - Disposable failed mission was requeued through `POST /api/missions/{mission_id}/resume` and then removed.
- Mission Approval Continuity verification: PASS
  - Full OTH test suite passed with exit code 0 before live endpoint validation.
  - Policy-blocked mission became durable `blocked` with approval metadata.
  - Live Console HTTP approval endpoint requeued the exact blocked task.
  - `approved_by=operator` persisted and the mission returned to `queued`.
  - Disposable validation mission/task rows were removed after the check.
- Mission Observability and Execution Timeline verification: PASS
  - Focused mission bridge timeline test passed.
  - Full OTH test suite passed with exit code 0.
  - Live Console timeline endpoint returned 9 correlated events for a real disposable mission.
  - Mission lifecycle events and underlying task events were both present.
  - Disposable mission/task/timeline records were removed after the check.
- Mission Cancellation and Graceful Intervention verification: PASS
  - Focused cancellation suite: PASS (3/3).
  - Full OTH pytest suite: PASS (100%, exit code 0, runtime ~36.9s after the final fix).
  - Real Console `GET /api/missions/{mission_id}/control`: PASS.
  - Real Console `POST /api/missions/{mission_id}/control` cancellation: PASS.
  - Blocked disposable mission was exposed as cancellation-eligible.
  - Cancellation requeued no work; it converted the exact blocked task to `cancelled`.
  - Mission timeline contained task and mission cancellation events.
  - Reconciliation persisted a durable `completed_at` timestamp for the first terminal cancellation transition.
  - Disposable mission/task/timeline rows were removed after validation.
  - Console was restarted from the intended VBS startup path after the final source fix.
- Mission Deadline and Watchdog verification: PASS
  - Focused deadline suite: PASS (3/3).
  - Full OTH pytest suite: PASS (100%, exit code 0, runtime ~22.2s).
  - Existing mission databases migrated in place with deadline/watchdog columns.
  - Real Console deadline API accepted a past deadline and the mission became `watchdog_status=overdue`.
  - Unified control response exposed the deadline timestamp, watchdog state, and overdue duration.
  - Mission timeline recorded `mission.deadline_set` and `mission.deadline_exceeded`.
  - Daemon runner invokes the watchdog each cycle without mutating task execution state.
  - Disposable mission/task/timeline rows were removed after validation.
  - Documentation: `docs/MISSION_DEADLINE.md`.
- Mission SLA Escalation verification: PASS
  - Focused mission deadline/escalation suite: PASS (5/5).
  - Full OTH pytest suite: PASS (100%, exit code 0, runtime 23.06s).
  - Pycompile of changed Python files: PASS.
  - git diff --check: PASS.
  - Live Console API policy persistence: PASS.
  - Live clock-relative escalation transition: PASS (warning -> critical -> overdue).
  - Live timeline contained mission.escalation_policy_set, mission.escalation_warning, mission.escalation_critical, and mission.deadline_exceeded.
  - Disposable validation mission and timeline rows were removed after validation.
  - Documentation: docs/MISSION_ESCALATION.md.
- Mission Progress and ETA verification: PASS
  - Focused progress suite: PASS (2/2).
  - Full OTH pytest suite: PASS (100%, exit code 0, runtime 27.10s).
  - Live Console progress endpoint: PASS.
  - Live unified control progress: PASS.
  - Disposable real mission reported 50% completion with 1/2 terminal tasks.
  - Observed 60-second cycle history produced a 60-second ETA.
  - No-history ETA suppression remains covered by focused tests.
  - Disposable validation mission/task/timeline rows were removed after validation.
  - Console was restarted through the intended VBS startup path.
  - Documentation: docs/MISSION_PROGRESS.md.
- Mission Attention Inbox verification: PASS
  - Focused attention suite: PASS (3/3).
  - Full OTH pytest suite: PASS (100%, exit code 0, runtime 43.77s).
  - Live Console created a critical deadline attention item.
  - Global attention inbox exposed the item.
  - Unified mission control exposed the same open attention.
  - Live acknowledgment persisted acknowledged_by=operator.
  - Acknowledged item disappeared from open global and mission queues.
  - Disposable mission/timeline/attention rows were removed after validation.
  - Console and daemon were restarted through their approved wrapper paths.
  - Documentation: docs/MISSION_ATTENTION.md.
- Mission Control Plane verification: PASS
  - Focused Mission Control regression tests: PASS (2/2).
  - Full OTH test suite: PASS (100%, exit code 0, runtime ~40.6s).
  - Real Console HTTP `GET /api/missions/{mission_id}/control`: PASS.
  - Real Console HTTP `POST /api/missions/{mission_id}/control` approval: PASS.
  - Blocked disposable mission exposed the exact approval-eligible task.
  - Approval requeued that exact task and persisted `approved_by=operator`.
  - Unified control response returned updated mission, graph, timeline, and action availability.
  - Disposable mission/task/timeline records were removed after validation.
  - Console and daemon duplicate-process cleanup was performed; the authoritative PID-file processes remain.
- A real console mission previously exposed a false-positive success bug; this was corrected and committed.
- Commit pushed:
  - `730720b` — `fix: reject false-positive native engineering success`

### Important lessons discovered
1. Passing pytest is NOT proof that an engineering mission was implemented.
2. Git status alone is NOT proof of change when the repository is already dirty.
3. The kernel must independently validate engineering evidence.
4. Pilot semantic routing previously misclassified a mission containing “production code”; the deterministic technical-intent guard now routes that class of mission to `engineering/execute`, with regression coverage.
5. The native and OpenCode workers can now honestly return failure when a requested implementation produces no observable repository change.

### Runtime
- OTH Console: port 18765
- OTH daemon: managed through Startup hook `OTH-Daemon.vbs`
- Do not manually spawn duplicate daemons.
- Current intended daemon startup path:
  `wscript.exe "...\\Startup\\OTH-Daemon.vbs"`

- Mission Operator Audit Ledger subsystem:
  - Durable `mission_audit` ledger in `data/console.db`.
  - Operator mutations are recorded with actor, action, result, payload, timestamp, previous hash, and entry hash.
  - Hash chaining makes ledger tampering detectable without changing the existing mission timeline semantics.
  - Covered mutations include mission creation, deadline set/clear, escalation policy changes, task approval, mission resume, mission cancellation, and attention acknowledgement.
  - CLI: `python -m oth.cli mission audit <mission_id> [--limit N] [--verify]`.
  - Console API: `GET /api/missions/{mission_id}/audit`.
  - Unified Mission Control now exposes `audit` and `audit_integrity`.
  - Documentation: `docs/MISSION_AUDIT.md`.

### Verification achieved
- Mission Operator Audit Ledger focused tests: PASS (5/5).
- Full OTH pytest suite: PASS (100%, exit code 0, runtime ~23.72s).
- Pycompile and `git diff --check`: PASS.
- Live Console audit flow: PASS.
  - Existing Console restarted on port 18765 with the migrated audit schema.
  - Disposable live mission created and exercised through HTTP.
  - Past deadline produced `mission.deadline_exceeded`.
  - Critical attention item was acknowledged through the live API.
  - Mission control exposed a valid audit ledger and `audit_integrity.valid=true`.
  - Live audit contained `mission.created`, `mission.deadline.set`, and `attention.acknowledge`.
  - Disposable audit/mission/timeline rows were removed after validation; remaining ledger integrity stayed valid.

- Mission Forensics and Replay subsystem:
  - Reconstructs a mission as a bounded chronological evidence stream from mission timeline events, underlying task events, and operator audit entries.
  - Replay includes mission state, reachable task graph, audit integrity, evidence counts, time bounds, source/kind summaries, and deterministic sequence numbers.
  - Read-only CLI: python -m oth.cli mission replay <mission_id> --limit N.
  - Console API: GET /api/missions/{mission_id}/replay.
  - Mission Control loads replay through the dedicated endpoint without inflating the normal control snapshot.
  - Documentation: docs/MISSION_REPLAY.md.

### Verification achieved
- Mission Forensics and Replay focused suite: PASS (5/5).
- Mission Replay + Audit focused regression: PASS (10/10).
- Full OTH pytest suite after implementation: PASS (100%, exit code 0, runtime 24.09s).
- Pycompile and git diff --check: PASS.
- Live Console replay validation: PASS.
  - Existing Console restarted on port 18765.
  - Disposable live mission reconstructed mission + audit evidence with valid integrity.
  - Three-stream validation reconstructed mission timeline + task event + operator audit in one replay.
  - Replay exposed all three sources: mission, task_event, and audit.
  - Task event and audit records were both present.
  - Disposable mission, timeline, audit, and task/event rows were removed after validation.
  - A disposable cleanup helper initially referenced a nonexistent DB method; cleanup was then completed directly and the workspace was rechecked clean.

- Mission Resource Guardrails subsystem:
  - Durable mission execution limits: `max_tasks` (default 256) and `max_retries` (default 8).
  - Task creation with a mission ID is blocked when the reachable mission graph already reaches the task cap.
  - Retry scheduling is blocked when the mission-wide retry cap is exhausted.
  - Budget exhaustion becomes durable mission timeline state and a critical `mission.budget_exhausted` attention item.
  - Operator can increase/decrease limits without automatically resuming or dispatching blocked work.
  - CLI: `python -m oth.cli mission budget <mission_id> [--max-tasks N] [--max-retries N]`.
  - Console API: `GET/POST /api/missions/{mission_id}/budget`.
  - Unified Mission Control exposes live budget counts, limits, remaining capacity, and status.
  - Budget policy changes are recorded in the operator audit ledger.
  - Documentation: `docs/MISSION_BUDGET.md`.

### Verification achieved
- Mission Resource Guardrails focused suite: PASS (5/5).
- Deadline + Budget + Audit + Replay regression suite: PASS (20/20).
- Full OTH pytest suite after final implementation: PASS (100%, exit code 0, runtime 23.70s).
- Pycompile and `git diff --check`: PASS.
- Fixed one pre-existing clock-sensitive deadline test by allowing `set_deadline(..., now=...)` so deterministic watchdog tests are independent of wall-clock time.
- Live Console budget flow: PASS.
  - Existing Console/daemon runtime was reconciled and restarted through approved wrappers.
  - `POST /api/missions/{mission_id}/budget` successfully set `max_tasks=1`.
  - A second mission task was created as `blocked` when the cap was reached.
  - Control surface reported `tasks_exhausted` and `mission.budget_exhausted`.
  - Increasing the cap to 3 restored budget status to `ok` without auto-dispatching the blocked task.
  - A real failed task with `max_retries=0` remained `failed` and did not schedule a retry.
  - Retry budget became `retries_exhausted` and surfaced budget attention.
  - Disposable mission/task/timeline/audit rows were removed after validation.

- Mission Policy Versioning and Governance subsystem:
  - Durable mission-scoped governance revisions in `mission_policy_revisions`.
  - Each revision pins approval, deadline, escalation, budget, and cancellation semantics.
  - Immutable revision number + SHA-256 policy hash.
  - Existing missions are backfilled into revision 1.
  - Deadline, escalation, budget, approval, and cancellation policy mutations create new revisions.
  - Kernel task policy checks use the mission-pinned approval policy instead of silently following the live global policy file.
  - Every `task.policy_evaluated` event records the active policy revision and hash.
  - Existing operator audit records automatically carry the active policy revision/hash.
  - CLI: `python -m oth.cli mission policy <mission_id>`.
  - Console API: `GET/POST /api/missions/{mission_id}/policy`.
  - Unified Mission Control exposes current policy revision/hash; forensic replay exposes revision history.
  - Documentation: `docs/MISSION_POLICY.md`.

### Verification achieved
- Mission Policy Versioning focused suite: PASS (6/6 after governance-evidence coverage).
- Adjacent policy/budget/deadline/audit/replay regression: PASS (25/25 before final evidence addition; 21/21 after evidence addition).
- Full OTH pytest suite after final governance implementation: PASS (100%, exit code 0, runtime 44.35s).
- Pycompile and `git diff --check`: PASS.
- Live governance validation: PASS.
  - Revision 1 required external approval and blocked a disposable external-risk task.
  - Revision 2 disabled that approval requirement.
  - A subsequent external-risk task succeeded.
  - `task.policy_evaluated` recorded revision 1/hash for the blocked decision and revision 2/hash for the allowed decision.
  - Control exposed current policy revision/hash.
  - Replay exposed policy revision history alongside mission and audit evidence.
  - Audit integrity remained valid.
  - Disposable mission/task/revision/timeline/audit rows were removed after validation.

### Current uncompleted item
None. Mission Policy Versioning and Governance is complete and live-validated.

### Next continuation point
Do not rebuild the established mission subsystems unless a regression appears. Continue with the next coherent OTH subsystem using the completed governance, control, evidence, and guardrail layers as infrastructure.





## Repository
Primary OTH directory:
`C:\Users\Admin\Documents\Over-The-Horizon`

Remote:
`https://github.com/Rizz-Gods/Apagain.git`

Do not bypass licenses, authentication, platform restrictions, or safety gates.
