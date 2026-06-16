# Test Coverage

This page describes how coverage is measured, reported, and enforced for both the backend
Python codebase and the frontend TypeScript codebase.

## Backend Coverage

### Configuration

Backend coverage is configured in `backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-report=term-missing -v"

[tool.coverage.run]
source = ["app"]
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

### Running Coverage

```bash
# From the backend/ directory

# Default: terminal report with missing lines
python -m pytest

# HTML report (opens in browser)
python -m pytest --cov=app --cov-report=html
open htmlcov/index.html

# XML report (for CI tools like Codecov, SonarQube)
python -m pytest --cov=app --cov-report=xml

# Multiple reporters at once
python -m pytest --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml

# Fail if coverage drops below threshold
python -m pytest --cov=app --cov-fail-under=80
```

### `--cov-report=term-missing` Output

The `term-missing` reporter prints a table showing which lines are not covered:

```
---------- coverage: platform darwin, python 3.11.9 ----------
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
app/__init__.py                             0      0   100%
app/agents/graph.py                       142     18    87%   45-47, 89, 201-215
app/agents/nodes/classical.py              38      2    95%   67, 71
app/agents/nodes/data_fetch.py             52      4    92%   88-91
app/agents/state.py                        12      0   100%
app/api/health.py                          34      0   100%
app/api/v1/assets.py                       28      0   100%
app/api/v1/optimize.py                     31      0   100%
app/api/v1/runs.py                         45      0   100%
app/api/websocket.py                       42      3    93%   78-80
app/core/config.py                         24      0   100%
app/core/dependencies.py                   18      0   100%
app/core/exceptions.py                     22      0   100%
app/data/metrics.py                        89      5    94%   134-138
app/data/sector_tags.py                    67      0   100%
app/engines/classical/optimizer.py         95      8    92%   112-119
app/engines/quantum/dispatcher.py          48      4    92%   67-70
app/engines/quantum/qaoa_qiskit.py         78      6    92%   89-94
app/engines/quantum/vqe_pennylane.py       71      5    93%   78-82
app/quantum/qubo.py                        56      0   100%
app/workers/celery_app.py                  18      0   100%
app/workers/tasks.py                       62      4    94%   98-101
---------------------------------------------------------------------
TOTAL                                    1182     59    95%
```

### Reading the Coverage Report

| Column | Meaning |
|--------|---------|
| `Stmts` | Total executable statements in the file |
| `Miss` | Statements not executed during the test run |
| `Cover` | Percentage of statements executed (`(Stmts - Miss) / Stmts * 100`) |
| `Missing` | Line numbers of uncovered statements |

**Interpreting missing lines:**

- Lines like `45-47` indicate a contiguous block (e.g., an error handler that was never triggered)
- Single lines like `89` are often guard clauses or early returns
- Ranges like `201-215` often indicate an entire branch (e.g., a fallback code path)

### Excluded Paths

The `omit` setting in `[tool.coverage.run]` excludes:

| Pattern | Reason |
|---------|--------|
| `*/tests/*` | Test files themselves are not production code |
| `*/__init__.py` | Package init files contain no logic |

The `exclude_lines` patterns in `[tool.coverage.report]` exclude:

| Pattern | Reason |
|---------|--------|
| `pragma: no cover` | Explicit opt-out for untestable code |
| `def __repr__` | Debug representation methods |
| `raise NotImplementedError` | Abstract method stubs |
| `if TYPE_CHECKING:` | Type-only imports (never executed at runtime) |
| `@abstractmethod` | Abstract method decorators |

### Adding `# pragma: no cover`

Use the `pragma: no cover` comment to exclude specific lines or blocks from coverage:

```python
def _debug_dump(self) -> str:  # pragma: no cover
    """Only used during development debugging."""
    return f"<{self.__class__.__name__}: {self.__dict__}>"
```

```python
if sys.platform == "win32":  # pragma: no cover
    # Windows-specific code path
    ...
```

---

## Frontend Coverage

### Configuration

Frontend coverage is configured in `frontend/vite.config.ts`:

```typescript
test: {
  coverage: {
    provider: "v8",
    reporter: ["text", "lcov"],
    exclude: [
      "node_modules/",
      "src/test/",
      "**/*.d.ts",
      "**/*.config.*",
      "src/main.tsx",
    ],
  },
},
```

### Running Coverage

```bash
# From the frontend/ directory

# Run tests with coverage
npm run test:coverage

# Equivalent direct command
npx vitest run --coverage
```

The `text` reporter prints a summary table to the terminal. The `lcov` reporter writes
`coverage/lcov.info` which can be uploaded to coverage services.

### Excluded Paths

| Pattern | Reason |
|---------|--------|
| `node_modules/` | Third-party dependencies |
| `src/test/` | Test files themselves |
| `**/*.d.ts` | TypeScript declaration files (no runtime code) |
| `**/*.config.*` | Configuration files (vite.config.ts, etc.) |
| `src/main.tsx` | Application entry point (bootstrapping only) |

---

## Coverage Targets

The project targets the following coverage levels:

| Layer | Target | Rationale |
|-------|--------|-----------|
| Backend API endpoints | ≥ 95% | Critical user-facing paths |
| Backend optimization engines | ≥ 90% | Complex algorithmic code |
| Backend agent graph | ≥ 85% | Routing logic + error paths |
| Backend data layer | ≥ 90% | Data transformation correctness |
| Frontend components | ≥ 80% | UI rendering and interactions |
| Frontend hooks | ≥ 85% | State management logic |
| Frontend API client | ≥ 90% | Network layer correctness |

> **Note:** Coverage targets are aspirational guidelines. The CI gate (described below)
> enforces a minimum floor to prevent regressions.

---

## CI Coverage Gate

### Backend Gate

To fail the CI pipeline if coverage drops below a threshold, add `--cov-fail-under` to the
pytest command:

```bash
# Fail if total coverage < 80%
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

This can be set in `pyproject.toml` via `addopts`:

```toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-report=term-missing --cov-fail-under=80 -v"
```

### Frontend Gate

Vitest supports coverage thresholds in `vite.config.ts`:

```typescript
test: {
  coverage: {
    provider: "v8",
    thresholds: {
      lines: 80,
      functions: 80,
      branches: 75,
      statements: 80,
    },
  },
},
```

### CI Pipeline Integration

A typical CI workflow (e.g., GitHub Actions) would:

```yaml
# .github/workflows/test.yml
jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -e ".[dev]"
        working-directory: backend
      - name: Run tests with coverage
        run: python -m pytest --cov=app --cov-report=xml --cov-fail-under=80
        working-directory: backend
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: backend/coverage.xml

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install dependencies
        run: npm ci
        working-directory: frontend
      - name: Run tests with coverage
        run: npm run test:coverage
        working-directory: frontend
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: frontend/coverage/lcov.info
```

---

## Coverage Report Interpretation

### Understanding Branch Coverage

Line coverage alone can miss untested branches. Consider:

```python
def get_status(services: dict) -> str:
    if all(v == "up" for v in services.values()):
        return "healthy"
    elif any(v == "up" for v in services.values()):
        return "degraded"
    else:
        return "unhealthy"
```

A test that only calls `get_status({"db": "up", "redis": "up"})` achieves 100% line
coverage but misses the `degraded` and `unhealthy` branches. The test suite explicitly
covers all three branches in `test_api_health.py`.

### Common Coverage Gaps

| Gap Type | Example | Mitigation |
|----------|---------|------------|
| Error handlers | `except ConnectionError:` | Add tests that inject connection failures |
| Fallback paths | `if result is None: return default` | Add tests with `None` inputs |
| Timeout handling | `asyncio.wait_for(..., timeout=30)` | Mock `asyncio.wait_for` to raise `TimeoutError` |
| Quantum fallback | Greedy selection when QAOA fails | Tests use greedy path by default |
| LLM explanation | OpenAI API call | Mock `langchain_openai` in tests |

### Viewing HTML Coverage Report

```bash
cd backend
python -m pytest --cov=app --cov-report=html
open htmlcov/index.html
```

The HTML report provides:
- **File-level summary** — sortable table of all files with coverage percentages
- **Line-level detail** — click any file to see green (covered) and red (missed) lines
- **Branch visualization** — partial branches shown in yellow

---

## Practical Tips

### Finding Untested Code Quickly

```bash
# Show only files with < 90% coverage
python -m pytest --cov=app --cov-report=term-missing 2>&1 | awk 'NR==1 || $4+0 < 90'
```

### Running Coverage for a Specific Module

```bash
# Only measure coverage for the agents module
python -m pytest ../tests/test_agent_graph.py --cov=app.agents --cov-report=term-missing
```

### Checking Coverage Without Running All Tests

```bash
# Run only fast unit tests for a quick coverage check
python -m pytest ../tests/test_classical_optimizer.py \
                 ../tests/test_quantum_qubo.py \
                 ../tests/test_data_metrics.py \
                 --cov=app --cov-report=term-missing
```
