# Over The Horizon (OTH)

[![Tests](https://github.com/Rizz-Gods/Apagain/actions/workflows/tests.yml/badge.svg)](https://github.com/Rizz-Gods/Apagain/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)

**A local-first, policy-gated workforce runtime for coordinating agents, tasks, and tools.**

Over The Horizon (OTH) is an experimental Python runtime that puts a task-oriented kernel between agents and the tools they use. It is designed around explicit execution state, replaceable workers, configurable policies, and evidence-backed outcomes.

The project is actively evolving. It is a developer tool and research codebase, not a security-certified or production-hardened automation platform.

## What it provides

- **Task execution kernel:** a SQLite-backed task lifecycle and dispatch layer.
- **Replaceable workers:** built-in, browser, and external worker adapters behind a common execution model.
- **Agent and skill registries:** declarative configuration for the capabilities available to the runtime.
- **Policy gates:** risk-aware decisions, with external and financial actions requiring approval by default in the checked-in policy configuration.
- **Mission control and auditability:** task graphs, mission state, timelines, audit records, integrity checks, and recovery-oriented workflows.
- **Model and execution routing:** configurable routing and fallback paths for supported local and external execution lanes.
- **Operator interfaces:** a command-line entry point and a local control console.

See [the engineering execution contract](docs/ENGINEERING_EXECUTION_CONTRACT.md) and the mission-control documents in `docs/` for implementation details.

## Requirements

- Python 3.11 or newer
- Git

Some optional capabilities depend on local applications, operating-system features, media tooling, or external providers. Those integrations may require additional configuration.

## Install

Clone the repository and install the project with its development dependencies:

```bash
git clone https://github.com/Rizz-Gods/Apagain.git
cd Apagain

python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the test suite

```bash
python -m pytest
```

The project also exposes the `oth` command-line entry point:

```bash
oth --help
```

## Project layout

```text
oth/
  core/       Kernel, policies, registries, routing, mission state, and services
  workers/    Built-in, browser, and external worker adapters
config/       Agent, skill, policy, model-routing, and runtime configuration
docs/         Engineering and mission-control contracts
tests/        Automated tests
ops/          Local operational helpers
```

## Safety model and operational guidance

The policy layer is intended to make consequential actions explicit. The default configuration requires approval for external and financial actions. Do not assume this makes every tool or workflow safe.

- Start with local, non-destructive tasks and least-privilege credentials.
- Keep API keys, OAuth tokens, passwords, personal data, databases, logs, and machine-specific state out of commits.
- Review worker permissions and provider configuration before enabling integrations.
- Test against disposable data and isolated environments before connecting real accounts or production systems.
- Treat generated plans and agent output as untrusted until independently checked.

**Do not use this project for unattended financial activity, safety-critical systems, or production automation without your own threat modelling, testing, and approval controls.**

## Contributing

Bug reports, tests, documentation, and focused pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request and follow the project's [Code of Conduct](CODE_OF_CONDUCT.md).

For security-sensitive reports, see [SECURITY.md](SECURITY.md).

## License

This project is distributed under the [MIT License](LICENSE).
