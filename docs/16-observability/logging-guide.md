# Logging Guide

The Portfolio Optimizer uses [structlog](https://www.structlog.org/) for structured logging throughout the backend. All log output is machine-parseable JSON in production and human-readable coloured text in development. Every log entry carries consistent contextual fields that make it easy to trace a specific optimization run across all components.

Logging is configured in `backend/app/core/logging.py` and initialised at application startup in `backend/app/main.py`.

---

## Configuration

### `configure_logging()`

```python
# backend/app/core/logging.py
def configure_logging(log_level: str = "INFO", environment: str = "development") -> None:
    """Configure structlog and stdlib logging.

    Call this once at application startup (in main.py lifespan).

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        environment: 'development' uses ConsoleRenderer; all others use JSONRenderer.
    """
```

This function is called once during the FastAPI lifespan startup:

```python
# backend/app/main.py
configure_logging(
    log_level=settings.LOG_LEVEL,
    environment=settings.ENVIRONMENT,
)
```

The `LOG_LEVEL` and `ENVIRONMENT` values come from environment variables (see `backend/app/core/config.py`).

### Shared Processors

The following processors run in every environment:

| Processor | Purpose |
|---|---|
| `merge_contextvars` | Merges context variables bound via `structlog.contextvars.bind_contextvars()` |
| `add_logger_name` | Adds the `logger` field with the module name |
| `add_log_level` | Adds the `level` field (`debug`, `info`, `warning`, `error`, `critical`) |
| `PositionalArgumentsFormatter` | Formats positional `%s`-style arguments |
| `TimeStamper(fmt="iso")` | Adds the `timestamp` field in ISO 8601 format |
| `StackInfoRenderer` | Renders stack info for exceptions |

### Renderer Selection

The renderer is chosen based on the `ENVIRONMENT` setting:

| Environment | Renderer | Output |
|---|---|---|
| `development` | `ConsoleRenderer(colors=True)` | Human-readable, coloured, aligned |
| `staging`, `production`, any other | `JSONRenderer()` | Machine-parseable JSON, one object per line |

---

## Log Formats

### Production (JSON)

In production, each log entry is a single JSON object on one line. This format is compatible with CloudWatch Logs, Datadog, Loki, and most log aggregation platforms.

```json
{
  "timestamp": "2026-06-15T10:23:45.123456Z",
  "level": "info",
  "logger": "app.agents.nodes",
  "event": "data_fetch_completed",
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "valid_tickers": ["AAPL", "MSFT", "GOOGL"],
  "num_days": 365,
  "elapsed_ms": 842.3
}
```

```json
{
  "timestamp": "2026-06-15T10:23:46.456789Z",
  "level": "error",
  "logger": "app.agents.nodes",
  "event": "data_fetch_failed",
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "error": "Connection timeout after 30s",
  "error_type": "TimeoutError",
  "elapsed_ms": 30001.0
}
```

### Development (Console)

In development, structlog renders coloured, human-readable output:

```
2026-06-15T10:23:45.123456Z [info     ] data_fetch_completed           logger=app.agents.nodes run_id=a1b2c3d4 valid_tickers=['AAPL','MSFT','GOOGL'] num_days=365 elapsed_ms=842.3
2026-06-15T10:23:46.456789Z [error    ] data_fetch_failed              logger=app.agents.nodes run_id=a1b2c3d4 error=Connection timeout error_type=TimeoutError elapsed_ms=30001.0
```

---

## Getting a Logger

Every module obtains a logger via `get_logger()`:

```python
# backend/app/core/logging.py
def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog BoundLogger bound with the given module name."""
    return structlog.get_logger(name)
```

Usage in any module:

```python
from app.core.logging import get_logger

logger = get_logger(__name__)

logger.info("optimization_started", run_id=str(run_id), tickers=tickers)
logger.warning("quantum_skipped_too_many_assets", run_id=run_id, num_assets=12)
logger.error("data_fetch_failed", run_id=run_id, error=str(exc), exc_info=True)
```

---

## Standard Log Fields

The following fields appear consistently across all log entries. Use them to filter and correlate logs in your aggregation platform.

| Field | Type | Description | Example |
|---|---|---|---|
| `timestamp` | string (ISO 8601) | Log entry timestamp in UTC | `"2026-06-15T10:23:45.123456Z"` |
| `level` | string | Log level | `"info"`, `"warning"`, `"error"` |
| `logger` | string | Module name (from `__name__`) | `"app.agents.nodes"` |
| `event` | string | Snake_case event name | `"data_fetch_completed"` |
| `run_id` | string (UUID) | Optimization run identifier | `"a1b2c3d4-..."` |
| `node` | string | Agent node name | `"data_fetch"`, `"classical_optimization"` |
| `error` | string | Error message | `"Connection timeout after 30s"` |
| `error_type` | string | Exception class name | `"TimeoutError"` |
| `path` | string | HTTP request path | `"/api/v1/optimize"` |
| `method` | string | HTTP method | `"POST"` |
| `elapsed_ms` | float | Operation duration in milliseconds | `842.3` |

### `run_id`

The `run_id` is a UUID assigned to each optimization request. It is threaded through every log entry in the agent pipeline, making it the primary correlation key for tracing a single optimization run end-to-end.

```python
# backend/app/agents/nodes.py
logger.info(
    "data_fetch_started",
    run_id=state.get("run_id"),
    tickers=tickers,
    lookback_days=lookback_days,
)
```

### `node`

The `node` field identifies which LangGraph agent node produced the log entry. It appears in node-level start, completion, and error events.

```python
logger.info(
    "constraint_validation_completed",
    run_id=state.get("run_id"),
    num_warnings=len(warnings),
    elapsed_ms=round(elapsed_ms, 1),
)
```

### `error` and `error_type`

Error events include both the human-readable error message and the Python exception class name for programmatic filtering.

```python
logger.error(
    "data_fetch_failed",
    run_id=state.get("run_id"),
    error=str(exc),
    error_type=type(exc).__name__,
    elapsed_ms=round(elapsed_ms, 1),
    exc_info=True,  # Includes full stack trace in the log entry
)
```

### `path` and `method`

HTTP request context fields appear in exception handler logs:

```python
# backend/app/main.py
logger.warning(
    "domain_error",
    error_code=exc.error_code,
    message=exc.message,
    path=str(request.url),
)

logger.error(
    "unhandled_exception",
    exc_type=type(exc).__name__,
    message=str(exc),
    path=str(request.url),
    exc_info=True,
)
```

---

## Log Levels Per Component

| Component | Module | Default Level | Key Events |
|---|---|---|---|
| Application startup | `app.main` | INFO | `application_starting`, `application_stopping` |
| Prometheus setup | `app.main` | INFO/WARNING | `prometheus_instrumentation_enabled`, `prometheus_instrumentation_unavailable` |
| Agent graph | `app.agents.graph` | INFO | `agent_graph_started`, `agent_graph_completed` |
| Agent nodes | `app.agents.nodes` | INFO/ERROR | `data_fetch_started`, `classical_optimization_completed`, etc. |
| LLM explainer | `app.agents.explainer` | INFO/WARNING | `llm_explanation_calling_gpt4o`, `llm_explanation_completed` |
| Comparison node | `app.agents.comparison` | INFO/DEBUG | `comparison_no_classical_result`, `comparison_completed` |
| Classical optimizer | `app.engines.classical` | INFO/WARNING | `efficient_frontier_computed`, `max_sharpe_optimization_complete` |
| Redis cache | `app.data.cache` | WARNING | Cache errors (graceful degradation) |
| Data fetcher | `app.data.fetcher` | INFO | Market data fetch events |
| Celery tasks | `app.workers.tasks` | INFO/ERROR | Task lifecycle events |
| HTTP access | `uvicorn.access` | WARNING | Silenced (too noisy) |
| SQLAlchemy | `sqlalchemy.engine` | WARNING | Silenced (too noisy) |
| httpx | `httpx` | WARNING | Silenced (too noisy) |

> **Silenced loggers**: `uvicorn.access`, `sqlalchemy.engine`, `httpx`, and `httpcore` are set to `WARNING` level to suppress their verbose INFO output. Override this in `configure_logging()` if you need SQL query logging during debugging.

---

## Key Log Events Reference

### Application Lifecycle

| Event | Level | Fields |
|---|---|---|
| `application_starting` | INFO | `environment`, `log_level` |
| `application_shutting_down` | INFO | — |
| `application_stopped` | INFO | — |
| `prometheus_instrumentation_enabled` | INFO | `endpoint` |
| `prometheus_instrumentation_unavailable` | WARNING | `reason` |

### Agent Graph

| Event | Level | Fields |
|---|---|---|
| `agent_graph_started` | INFO | `run_id`, `tickers`, `budget`, `run_quantum` |
| `agent_graph_completed` | INFO | `run_id`, `completed_nodes`, `has_error`, `failed_node`, `total_timings_ms` |
| `frontier_skipped_no_classical_result` | INFO | `run_id` |
| `quantum_skipped_disabled` | INFO | `run_id` |
| `quantum_skipped_too_many_assets` | WARNING | `run_id`, `num_assets`, `max_assets` |
| `classical_result_deserialisation_failed` | WARNING | `run_id`, `error` |
| `quantum_result_deserialisation_failed` | WARNING | `run_id`, `error` |

### Data Fetch Node

| Event | Level | Fields |
|---|---|---|
| `data_fetch_started` | INFO | `run_id`, `tickers`, `lookback_days` |
| `data_fetch_completed` | INFO | `run_id`, `valid_tickers`, `num_days`, `elapsed_ms` |
| `data_fetch_failed` | ERROR | `run_id`, `error`, `error_type`, `elapsed_ms` |

### Constraint Validation Node

| Event | Level | Fields |
|---|---|---|
| `constraint_validation_started` | INFO | `run_id`, `num_tickers` |
| `constraint_validation_completed` | INFO | `run_id`, `num_warnings`, `elapsed_ms` |
| `constraint_validation_failed` | ERROR | `run_id`, `error`, `error_type`, `elapsed_ms` |
| `constraint_warnings_detected` | WARNING | `run_id`, `warnings` |

### LLM Explainer

| Event | Level | Fields |
|---|---|---|
| `llm_explanation_calling_gpt4o` | INFO | — |
| `llm_explanation_completed` | INFO | `tokens_used`, `elapsed_ms` |

---

## Log Aggregation Recommendations

### CloudWatch Logs (AWS)

When deploying on AWS ECS or EC2, configure the Docker log driver to send container stdout to CloudWatch Logs:

```json
{
  "logDriver": "awslogs",
  "options": {
    "awslogs-group": "/portfolio-optimizer/backend",
    "awslogs-region": "us-east-1",
    "awslogs-stream-prefix": "backend"
  }
}
```

In CloudWatch Logs Insights, use the JSON field extraction to query structured fields:

```sql
-- Find all log entries for a specific run_id
fields @timestamp, level, event, node, elapsed_ms
| filter run_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
| sort @timestamp asc

-- Find all errors in the last hour
fields @timestamp, event, error, error_type, run_id
| filter level = "error"
| sort @timestamp desc
| limit 50

-- Slow data fetch operations (> 5 seconds)
fields @timestamp, run_id, elapsed_ms
| filter event = "data_fetch_completed" and elapsed_ms > 5000
| sort elapsed_ms desc
```

### Grafana Loki

If using Loki for log aggregation, configure Promtail to scrape Docker container logs and add labels:

```yaml
# promtail-config.yml
scrape_configs:
  - job_name: portfolio-optimizer
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
    relabel_configs:
      - source_labels: [__meta_docker_container_name]
        target_label: container
    pipeline_stages:
      - json:
          expressions:
            level: level
            event: event
            run_id: run_id
      - labels:
          level:
          event:
```

LogQL queries in Grafana:

```logql
# All logs for a specific run_id
{container="portfolio-optimizer-backend"} | json | run_id="a1b2c3d4-..."

# Error rate over time
sum(rate({container="portfolio-optimizer-backend"} | json | level="error" [5m]))

# Slow optimization runs
{container="portfolio-optimizer-backend"} | json | event="agent_graph_completed" | elapsed_ms > 60000
```

### Elasticsearch / OpenSearch

Configure Filebeat or Fluentd to ship logs to Elasticsearch. The JSON format is directly compatible with Elasticsearch's JSON ingest pipeline.

---

## Searching Logs for a Specific `run_id`

The `run_id` is the primary key for tracing an optimization run. Here are platform-specific search patterns:

### Docker (local development)

```bash
# Stream logs for a specific run_id
docker logs portfolio-optimizer-backend 2>&1 | grep "a1b2c3d4"

# Using jq for structured filtering
docker logs portfolio-optimizer-backend 2>&1 | \
  jq -c 'select(.run_id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890")'
```

### CloudWatch Logs Insights

```sql
fields @timestamp, level, event, node, elapsed_ms, error
| filter run_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
| sort @timestamp asc
```

### Grafana Loki (LogQL)

```logql
{job="portfolio-optimizer"} | json | run_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### Kibana (KQL)

```
run_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### Typical Log Sequence for a Successful Run

When tracing a successful optimization run, you should see these events in order:

```
agent_graph_started          → run_id, tickers, budget, run_quantum
data_fetch_started           → run_id, tickers, lookback_days
data_fetch_completed         → run_id, valid_tickers, num_days, elapsed_ms
constraint_validation_started → run_id, num_tickers
constraint_validation_completed → run_id, num_warnings, elapsed_ms
classical_optimization_started → run_id
classical_optimization_completed → run_id, sharpe_ratio, elapsed_ms
quantum_dispatch_started     → run_id, solver
quantum_dispatch_completed   → run_id, solver, elapsed_ms
comparison_completed         → run_id, winner, elapsed_ms
llm_explanation_calling_gpt4o → (no run_id — LLM node)
llm_explanation_completed    → tokens_used, elapsed_ms
agent_graph_completed        → run_id, completed_nodes, has_error=false
```

If `has_error=true` appears in `agent_graph_completed`, look for the corresponding `*_failed` event earlier in the sequence to identify the failing node.

---

## Related Pages

- [Prometheus Metrics](prometheus-metrics.md) — metrics exposed alongside logs
- [Alertmanager](alertmanager.md) — alert rules that fire based on error rates
- [Backend Configuration](../03-backend/configuration.md) — `LOG_LEVEL` and `ENVIRONMENT` settings
- [Backend Logging](../03-backend/logging.md) — detailed structlog configuration reference
