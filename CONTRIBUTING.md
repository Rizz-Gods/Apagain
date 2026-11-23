# Contributing to Over The Horizon

Thanks for considering a contribution.

## Before you start

- Search existing issues and pull requests before opening a duplicate.
- For significant changes, open an issue or discussion first so the design can be reviewed.
- Keep pull requests focused. Explain the problem, the intended behaviour, and any trade-offs.
- Never include real credentials, OAuth tokens, private account data, production databases, logs, or machine-specific paths in commits.

## Development setup

The project requires Python 3.11 or newer.

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Tests

Run the complete test suite before submitting:

```bash
python -m pytest
```

Add or update tests for behaviour changes. Prefer isolated temporary directories and test data; tests should not depend on personal accounts, live credentials, or production services.

## Pull request checklist

- [ ] The change has a clear purpose and is limited in scope.
- [ ] Tests cover the changed behaviour.
- [ ] The full test suite passes locally.
- [ ] Documentation and configuration examples are updated where needed.
- [ ] No secrets, private data, generated state, or machine-specific files are included.
- [ ] Failure modes and approval requirements remain explicit.

By participating, you agree to follow the project's Code of Conduct.
