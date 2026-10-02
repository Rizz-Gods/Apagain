# Over The Horizon

Autonomous workforce kernel.

## Milestone 0.1

- Task queue backed by SQLite
- Replaceable worker interface
- Skill registry
- Agent registry
- Event log
- Safe default policy configuration
- CLI for task submission and execution

The first worker is intentionally tiny: a deterministic echo worker.
It exists to prove the kernel contract before real agents are attached.
