# CI Workflow (`ci.yml`)

The Continuous Integration workflow runs on every push to any branch and on every pull request targeting `main` or `develop`. It validates code quality, runs the full test suite, builds production Docker images, and performs a security scan — all before any code reaches a deployment environment.

## Overview

```mermaid
graph TD
    A["Push / PR"] --> B["lint-backend"]
    A --> C["test-backend"]
    A --> D["lint-frontend"]
    A --> E["test-frontend"]
    C --> F["build-backend"]
    E --> G["build-frontend"]
    F --> H["security-scan"]
    G --> H
```

All lint and test jobs run in parallel. The Docker build jobs depend on their respective test jobs passing, and the security scan runs only after both images are built successfully.

## Triggers

```yaml
on:
  push:
    branches: ["**"]          # every branch push triggers CI
  pull_request:
    branches: [main, develop] # PRs targeting main or develop
```

Every developer branch gets CI feedback on push. Pull requests to the protected `main` and `develop` branches must pass all CI checks before merging is allowed.

## Concurrency Group

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

Only one CI run per branch/PR is active at a time. If a new commit is pushed while a run is in progress, the older run is cancelled automatically. This prevents queue buildup during rapid iteration and reduces GitHub Actions minutes consumption.

## Caching Strategy

Effective caching is critical for a project with heavy scientific Python dependencies (NumPy, SciPy, CVXPY, Qiskit, PennyLane) and a full Node.js frontend.

### Python (pip) Cache

```yaml
- name: Cache pip dependencies
  uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: pip-${{ runner.os }}-${{ hashFiles('backend/pyproject.toml') }}
    restore-keys: |
      pip-${{ runner.os }}-
```

The cache key is derived from a hash of `backend/pyproject.toml`. Any change to the dependency manifest (adding, removing, or upgrading a package) produces a new cache key, ensuring a clean install. The `restore-keys` fallback allows partial cache hits when only some dependencies changed.

### Node.js (npm) Cache

```yaml
- name: Cache npm dependencies
  uses: actions/cache@v4
  with:
    path: ~/.npm
    key: npm-${{ runner.os }}-${{ hashFiles('frontend/package-lock.json') }}
    restore-keys: |
      npm-${{ runner.os }}-
```

The npm cache key is derived from `package-lock.json` — the lock file guarantees exact reproducibility. `npm ci` (used in all CI steps) reads from this lock file and validates the cache integrity.

## Jobs

### `lint-backend`

Runs Ruff (linting + formatting check) and mypy (static type checking) against the FastAPI backend.

```yaml
lint-backend:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: backend
  steps:
    - uses: actions/checkout@v4

    - name: Set up Python 3.11
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: Cache pip dependencies
      uses: actions/cache@v4
      with:
        path: ~/.cache/pip
        key: pip-${{ runner.os }}-${{ hashFiles('backend/pyproject.toml') }}
        restore-keys: pip-${{ runner.os }}-

    - name: Install dev dependencies
      run: pip install -e ".[dev]"

    - name: Run Ruff linter
      run: ruff check .

    - name: Run Ruff formatter check
      run: ruff format --check .

    - name: Run mypy type checker
      run: mypy app/ --ignore-missing-imports
```

**Ruff** is configured via `pyproject.toml` and enforces PEP 8 style, import ordering, and common bug patterns. It replaces flake8, isort, and pyupgrade in a single fast tool.

**mypy** performs static type analysis across the `app/` package. The `--ignore-missing-imports` flag is used for third-party libraries that lack type stubs (e.g., some Qiskit sub-packages).

> **Note:** The `ruff format --check` step does not modify files — it exits with a non-zero code if any file would be reformatted, causing the job to fail. Developers should run `ruff format .` locally before pushing.

### `test-backend`

Runs the full pytest suite with coverage reporting.

```yaml
test-backend:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: backend
  services:
    postgres:
      image: postgres:16-alpine
      env:
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: postgres
        POSTGRES_DB: portfolio_optimizer_test
      ports: ["5432:5432"]
      options: >-
        --health-cmd "pg_isready -U postgres"
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5
    redis:
      image: redis:7-alpine
      ports: ["6379:6379"]
      options: >-
        --health-cmd "redis-cli ping"
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5
  steps:
    - uses: actions/checkout@v4

    - name: Set up Python 3.11
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: Cache pip dependencies
      uses: actions/cache@v4
      with:
        path: ~/.cache/pip
        key: pip-${{ runner.os }}-${{ hashFiles('backend/pyproject.toml') }}
        restore-keys: pip-${{ runner.os }}-

    - name: Install dependencies
      run: pip install -e ".[dev]"

    - name: Run pytest with coverage
      env:
        DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer_test
        REDIS_URL: redis://localhost:6379/0
        CELERY_BROKER_URL: redis://localhost:6379/1
        CELERY_RESULT_BACKEND: redis://localhost:6379/2
        ENVIRONMENT: test
        OPENAI_API_KEY: sk-test-placeholder
      run: |
        pytest ../tests/ \
          --cov=app \
          --cov-report=term-missing \
          --cov-report=xml:coverage.xml \
          --cov-fail-under=80 \
          -v

    - name: Upload coverage report
      uses: actions/upload-artifact@v4
      with:
        name: backend-coverage
        path: backend/coverage.xml
```

The test job spins up real PostgreSQL 16 and Redis 7 service containers using GitHub Actions' built-in `services` block. Tests run against these live services, matching the production stack as closely as possible.

The `pyproject.toml` configures pytest:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["../tests"]
addopts = "--cov=app --cov-report=term-missing -v"

[tool.coverage.run]
source = ["app"]
omit = ["*/tests/*", "*/__init__.py"]
```

Coverage is enforced at **80% minimum** (`--cov-fail-under=80`). The XML report is uploaded as an artifact for downstream consumption (e.g., Codecov integration).

### `lint-frontend`

Runs ESLint, Prettier format check, and TypeScript type checking against the React frontend.

```yaml
lint-frontend:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: frontend
  steps:
    - uses: actions/checkout@v4

    - name: Set up Node.js 20
      uses: actions/setup-node@v4
      with:
        node-version: "20"

    - name: Cache npm dependencies
      uses: actions/cache@v4
      with:
        path: ~/.npm
        key: npm-${{ runner.os }}-${{ hashFiles('frontend/package-lock.json') }}
        restore-keys: npm-${{ runner.os }}-

    - name: Install dependencies
      run: npm ci

    - name: Run ESLint
      run: npm run lint

    - name: Run Prettier format check
      run: npm run format:check

    - name: Run TypeScript type check
      run: npm run type-check
```

The `package.json` scripts map to:

| Script | Command | Purpose |
|--------|---------|---------|
| `lint` | `eslint . --max-warnings 0` | ESLint with zero-warning tolerance |
| `format:check` | `prettier --check "src/**/*.{ts,tsx,css}"` | Prettier format validation |
| `type-check` | `tsc --noEmit` | TypeScript compilation without output |

The `--max-warnings 0` flag on ESLint means any warning is treated as an error, enforcing strict code quality. The TypeScript check uses `tsc --noEmit` which validates types without producing build artifacts.

### `test-frontend`

Runs the Vitest test suite with V8 coverage.

```yaml
test-frontend:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: frontend
  steps:
    - uses: actions/checkout@v4

    - name: Set up Node.js 20
      uses: actions/setup-node@v4
      with:
        node-version: "20"

    - name: Cache npm dependencies
      uses: actions/cache@v4
      with:
        path: ~/.npm
        key: npm-${{ runner.os }}-${{ hashFiles('frontend/package-lock.json') }}
        restore-keys: npm-${{ runner.os }}-

    - name: Install dependencies
      run: npm ci

    - name: Run Vitest with coverage
      run: npm run test:coverage

    - name: Upload coverage report
      uses: actions/upload-artifact@v4
      with:
        name: frontend-coverage
        path: frontend/coverage/
```

Vitest uses `@vitest/coverage-v8` for native V8 coverage instrumentation. Tests use `@testing-library/react` and `jsdom` for component testing. The `test:coverage` script maps to `vitest run --coverage`.

### `build-backend`

Builds the production Docker image for the backend (FastAPI + Celery worker).

```yaml
build-backend:
  runs-on: ubuntu-latest
  needs: [test-backend]
  steps:
    - uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Build backend production image
      uses: docker/build-push-action@v6
      with:
        context: ./backend
        file: ./backend/Dockerfile
        target: production
        push: false
        tags: portfolio-optimizer-backend:${{ github.sha }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
        outputs: type=docker,dest=/tmp/backend-image.tar

    - name: Upload image artifact
      uses: actions/upload-artifact@v4
      with:
        name: backend-image
        path: /tmp/backend-image.tar
        retention-days: 1
```

The build targets the `production` stage of `backend/Dockerfile`, which:
- Installs only production dependencies (no dev extras)
- Copies `app/`, `alembic/`, and `alembic.ini`
- Creates a non-root `appuser` (UID 1001)
- Exposes port 8000 with a healthcheck

GitHub Actions Cache (`type=gha`) is used for BuildKit layer caching, dramatically reducing build times for unchanged layers. The image is exported as a tar file and uploaded as an artifact for the security scan job.

### `build-frontend`

Builds the production Docker image for the frontend (Nginx serving React static assets).

```yaml
build-frontend:
  runs-on: ubuntu-latest
  needs: [test-frontend]
  steps:
    - uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Build frontend production image
      uses: docker/build-push-action@v6
      with:
        context: ./frontend
        file: ./frontend/Dockerfile
        target: production
        push: false
        tags: portfolio-optimizer-frontend:${{ github.sha }}
        build-args: |
          VITE_API_BASE_URL=https://api.portfolio-optimizer.example.com
          VITE_WS_BASE_URL=wss://api.portfolio-optimizer.example.com
        cache-from: type=gha
        cache-to: type=gha,mode=max
        outputs: type=docker,dest=/tmp/frontend-image.tar

    - name: Upload image artifact
      uses: actions/upload-artifact@v4
      with:
        name: frontend-image
        path: /tmp/frontend-image.tar
        retention-days: 1
```

The frontend Dockerfile uses a multi-stage build:
1. **`base`** — Node 20 Alpine with `package.json` and `package-lock.json` copied
2. **`builder`** — Runs `npm ci` + `npm run build` (TypeScript compile + Vite bundle)
3. **`production`** — Nginx 1.27 Alpine serving the `/app/dist` static assets

Build arguments `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` are baked into the Vite bundle at build time. These are set to placeholder values in CI; the CD workflow overrides them with environment-specific URLs.

### `security-scan`

Runs Trivy vulnerability scanner against both production images.

```yaml
security-scan:
  runs-on: ubuntu-latest
  needs: [build-backend, build-frontend]
  steps:
    - name: Download backend image
      uses: actions/download-artifact@v4
      with:
        name: backend-image
        path: /tmp/

    - name: Download frontend image
      uses: actions/download-artifact@v4
      with:
        name: frontend-image
        path: /tmp/

    - name: Load images
      run: |
        docker load --input /tmp/backend-image.tar
        docker load --input /tmp/frontend-image.tar

    - name: Run Trivy on backend image
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: portfolio-optimizer-backend:${{ github.sha }}
        format: sarif
        output: trivy-backend.sarif
        severity: CRITICAL,HIGH
        exit-code: "1"

    - name: Run Trivy on frontend image
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: portfolio-optimizer-frontend:${{ github.sha }}
        format: sarif
        output: trivy-frontend.sarif
        severity: CRITICAL,HIGH
        exit-code: "1"

    - name: Upload Trivy SARIF results
      uses: github/codeql-action/upload-sarif@v3
      if: always()
      with:
        sarif_file: "."
```

Trivy scans for OS-level CVEs and language-specific vulnerabilities (Python packages, Node.js packages). The scan fails the CI pipeline on `CRITICAL` or `HIGH` severity findings. SARIF results are uploaded to GitHub Security tab for visibility.

> **Important:** The `exit-code: "1"` setting means any CRITICAL or HIGH CVE will block the build. Review and remediate findings before merging. Use `trivy image --ignore-unfixed` locally to filter out vulnerabilities with no available fix.

## Full Workflow File

The complete `ci.yml` lives at `.github/workflows/ci.yml`. Here is the skeleton showing job dependencies:

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:
    branches: [main, develop]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-backend:
    # ... Ruff + mypy

  test-backend:
    # ... pytest + coverage (needs: postgres + redis services)

  lint-frontend:
    # ... ESLint + Prettier + tsc

  test-frontend:
    # ... Vitest + coverage

  build-backend:
    needs: [test-backend]
    # ... Docker build --target production

  build-frontend:
    needs: [test-frontend]
    # ... Docker build --target production

  security-scan:
    needs: [build-backend, build-frontend]
    # ... Trivy CRITICAL+HIGH scan
```

## Related Pages

- [CD Workflow](cd-workflow.md) — deployment pipeline triggered after CI passes on `main`/`develop`
- [GitHub Secrets & Variables](github-secrets.md) — required secrets for CI and CD
- [Terraform Workflow](terraform-workflow.md) — infrastructure provisioning pipeline
