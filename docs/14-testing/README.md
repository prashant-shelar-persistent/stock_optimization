# Testing

Documentation for the full test suite — unit tests, integration tests, end-to-end smoke tests, pytest configuration, and coverage reporting.

## Section Contents

| Page | Description |
|------|-------------|
| [Backend Tests](../13-testing/backend-tests.md) | pytest suite, fixtures, mocking strategies, and test organization |
| [Frontend Tests](../13-testing/frontend-tests.md) | Vitest + React Testing Library component and hook tests |
| [Test Coverage](../13-testing/test-coverage.md) | Coverage configuration, thresholds, and reporting |
| [E2E Smoke Tests](../13-testing/e2e-smoke-tests.md) | End-to-end smoke test suite against a running stack |

## Testing Strategy

The Portfolio Optimizer uses a **three-tier testing strategy**:

```mermaid
graph TD
    A["Unit Tests<br/>(fast, isolated)"] --> B["Integration Tests<br/>(real DB, real Redis)"]
    B --> C["E2E Smoke Tests<br/>(full stack)"]
    style A fill:#4ade80
    style B fill:#facc15
    style C fill:#f87171
```

| Tier | Tool | Scope | Speed |
|------|------|-------|-------|
| **Unit** | pytest / Vitest | Individual functions and components | < 30s |
| **Integration** | pytest + testcontainers | API routes, DB, Redis | 1–3 min |
| **E2E Smoke** | pytest + httpx | Full stack (Docker Compose) | 3–10 min |

## Running Tests

```bash
# Backend unit + integration tests
cd backend
pytest tests/ -v --cov=app --cov-report=html

# Frontend tests
cd frontend
npm run test

# E2E smoke tests (requires running stack)
docker compose up -d
pytest tests/e2e/ -v
```

## Coverage Thresholds

| Component | Minimum Coverage |
|-----------|----------------|
| Backend (overall) | 80% |
| Optimization engines | 90% |
| API routes | 85% |
| Frontend components | 70% |

## Cross-References

- **CI pipeline runs tests** → [CI Workflow](../15-cicd/ci-workflow.md)
- **Backend configuration** → [Backend Configuration](../03-backend/configuration.md)
- **Agent layer testing** → [Backend Tests](../13-testing/backend-tests.md)
