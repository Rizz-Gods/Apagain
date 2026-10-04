# Over The Horizon — Mission State

## Current subsystem: Engineering Execution Reliability

Status: SUBSYSTEM COMPLETE AND LIVE-VALIDATED

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

### Current uncompleted item
None. Engineering Execution Reliability is complete and live-validated.

### Next continuation point
Do not rebuild or re-run the completed Engineering Execution subsystem unless a regression appears. Continue with the next coherent OTH subsystem from this checkpoint, using the engineering worker, evidence guard, evaluator, and scorecard as established infrastructure.

## Repository
Primary OTH directory:
`C:\Users\Admin\Documents\Over-The-Horizon`

Remote:
`https://github.com/Rizz-Gods/Apagain.git`

Do not bypass licenses, authentication, platform restrictions, or safety gates.
