# Contributing

Guidelines for contributing to the Portfolio Optimizer — code style (Ruff, mypy), branching strategy, pull request workflow, commit conventions, and local development setup.

## Overview

Contributions to the Portfolio Optimizer are welcome! This section covers everything you need to know to contribute effectively — from setting up your development environment to getting your pull request merged.

## Development Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/your-fork/stock_optimization.git
cd stock_optimization

# 2. Set up the backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Set up the frontend
cd ../frontend
npm install

# 4. Start the supporting services
docker compose up postgres redis -d

# 5. Run the test suite to verify your setup
cd ../backend
pytest tests/ -v
```

## Code Style

### Backend (Python)

| Tool | Purpose | Config |
|------|---------|--------|
| **Ruff** | Linting + formatting | `pyproject.toml` |
| **mypy** | Static type checking | `pyproject.toml` |
| **isort** | Import sorting (via Ruff) | `pyproject.toml` |

```bash
# Format and lint
ruff check --fix .
ruff format .
mypy app/
```

### Frontend (TypeScript)

| Tool | Purpose | Config |
|------|---------|--------|
| **ESLint** | Linting | `.eslintrc.json` |
| **Prettier** | Formatting | `.prettierrc` |
| **TypeScript** | Type checking | `tsconfig.json` |

```bash
npm run lint
npm run format
npm run type-check
```

## Branching Strategy

```
main          ← production-ready, protected
  └── develop ← integration branch
        ├── feature/your-feature-name
        ├── fix/bug-description
        └── chore/maintenance-task
```

## Pull Request Workflow

1. **Create a branch** from `develop`: `git checkout -b feature/my-feature`
2. **Write tests** for your changes (maintain coverage thresholds)
3. **Run the full test suite** locally before pushing
4. **Open a PR** against `develop` with a clear description
5. **CI must pass** — lint, type check, tests, coverage
6. **Request review** from at least one maintainer
7. **Squash and merge** once approved

## Commit Conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add VQE solver with PennyLane backend
fix: handle empty covariance matrix in MVO
docs: update QAOA solver documentation
test: add integration tests for optimize endpoint
chore: upgrade Qiskit to 1.x
refactor: extract constraint validation to separate module
```

## Cross-References

- **Local setup** → [Local Quickstart](../01-getting-started/quickstart-local.md)
- **Testing** → [Backend Tests](../13-testing/backend-tests.md)
- **CI pipeline** → [CI Workflow](../15-cicd/ci-workflow.md)
- **Architecture** → [System Overview](../02-architecture/system-overview.md)
