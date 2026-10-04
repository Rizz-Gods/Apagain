# Over The Horizon — Mission State

## Current subsystem: Engineering Execution Reliability

Status: SUBSYSTEM BUILT AND PERSISTED

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
- Contract documentation:
  - `docs/ENGINEERING_EXECUTION_CONTRACT.md`

### Verification achieved
- Focused engineering tests: PASS
- Full OTH test suite: PASS (current suite completed with exit code 0)
- Live scorecard command works.
- Live worker/evaluator history currently includes:
  - ollama-engineer: 1 recorded run, quality 1.0
  - opencode-engineer: 2 recorded runs, average quality 0.9375
- A real console mission previously exposed a false-positive success bug; this was corrected and committed.
- Commit pushed:
  - `730720b` — `fix: reject false-positive native engineering success`

### Important lessons discovered
1. Passing pytest is NOT proof that an engineering mission was implemented.
2. Git status alone is NOT proof of change when the repository is already dirty.
3. The kernel must independently validate engineering evidence.
4. Pilot semantic routing can still misclassify certain natural-language missions. One validation mission containing the phrase “production code” was routed to media-production; this was quarantined rather than counted as engineering success.
5. The native and OpenCode workers can now honestly return failure when a requested implementation produces no observable repository change.

### Runtime
- OTH Console: port 18765
- OTH daemon: managed through Startup hook `OTH-Daemon.vbs`
- Do not manually spawn duplicate daemons.
- Current intended daemon startup path:
  `wscript.exe "...\\Startup\\OTH-Daemon.vbs"`

### Current uncompleted item
A final live end-to-end Console validation task was manually submitted directly to the engineering capability. It is currently queued and has not been counted as completed. Do not claim the Engineering Execution subsystem failed because of that queue; the subsystem contract and tests are already complete.

### Next continuation point
Continue from the Engineering Execution subsystem and build the next coherent OTH subsystem. Prefer:
1. fix Pilot capability classification so explicit engineering missions reliably resolve to `engineering/execute`;
2. then run a real console-originated engineering mission using the fixed routing;
3. persist model/worker outcome metadata into the scorecard;
4. only then move to the next subsystem.

## Repository
Primary OTH directory:
`C:\Users\Admin\Documents\Over-The-Horizon`

Remote:
`https://github.com/Rizz-Gods/Apagain.git`

Do not bypass licenses, authentication, platform restrictions, or safety gates.
