# API Reference

Complete reference for the Portfolio Optimizer REST API (v1) and WebSocket gateway — endpoints, request/response schemas, error codes, and authentication.

## Section Contents

| Page | Description |
|------|-------------|
| [Optimize Endpoint](../04-api-reference/optimize-endpoint.md) | `POST /api/v1/optimize` — trigger an optimization run |
| [Runs Endpoints](../04-api-reference/runs-endpoints.md) | `GET /api/v1/runs` and `GET /api/v1/runs/{id}` — list and retrieve run history |
| [Assets Endpoint](../04-api-reference/assets-endpoint.md) | `GET /api/v1/assets` — available ticker universe |
| [Health Endpoint](../04-api-reference/health-endpoint.md) | `GET /health` — liveness and readiness probes |
| [WebSocket Endpoint](../04-api-reference/websocket-endpoint.md) | `WS /ws/runs/{id}/progress` — real-time progress streaming |
| [Error Codes](../04-api-reference/error-codes.md) | HTTP status codes, error response schema, and error catalog |

## Base URL

| Environment | Base URL |
|-------------|----------|
| Local (Docker) | `http://localhost:8000` |
| Local (bare-metal) | `http://localhost:8000` |
| Production | `https://api.your-domain.com` |

## API Overview

All REST endpoints are prefixed with `/api/v1/`. The API follows standard HTTP conventions:

| Method | Semantics |
|--------|-----------|
| `GET` | Read-only, idempotent |
| `POST` | Create a new resource or trigger an action |
| `DELETE` | Remove a resource |

### Authentication

The current version uses **API key authentication** via the `X-API-Key` header (configurable). In development mode with `DEBUG=true`, authentication is bypassed.

```http
POST /api/v1/optimize HTTP/1.1
Host: localhost:8000
Content-Type: application/json
X-API-Key: your-api-key-here

{
  "tickers": ["AAPL", "MSFT", "GOOGL"],
  "budget": 100000,
  "run_quantum": true
}
```

### Async Pattern

The optimize endpoint follows an **async request-reply** pattern:

1. `POST /api/v1/optimize` → returns `202 Accepted` with a `run_id`
2. Connect to `WS /ws/runs/{run_id}/progress` to receive real-time progress events
3. `GET /api/v1/runs/{run_id}` to retrieve the final result once complete

## Cross-References

- **Request/Response schemas** → [Request Schemas](../12-schemas/request-schemas.md) · [Response Schemas](../12-schemas/response-schemas.md)
- **Validation rules** → [Validation Rules](../12-schemas/validation-rules.md)
- **Task queue internals** → [Optimization Task](../10-task-queue/optimization-task.md)
- **Progress event format** → [Progress Events](../10-task-queue/progress-events.md)
