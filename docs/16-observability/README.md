# Observability

Prometheus metrics, Grafana dashboards, Alertmanager rules, and structured logging for the Portfolio Optimizer.

## Section Contents

| Page | Description |
|------|-------------|
| [Prometheus Metrics](prometheus-metrics.md) | Custom metrics, instrumentation, and scrape configuration |
| [Grafana Dashboards](grafana-dashboards.md) | Dashboard panels, PromQL queries, and provisioning |
| [Alertmanager](alertmanager.md) | Alert rules, severity levels, and notification routing |
| [Logging Guide](logging-guide.md) | Structured JSON log format, log levels, and querying with Loki |

## Observability Stack

```mermaid
graph LR
    subgraph "Application"
        API["FastAPI<br/>/metrics"]
        CEL["Celery Workers<br/>(custom metrics)"]
    end
    subgraph "Collection & Storage"
        PROM["Prometheus"]
    end
    subgraph "Visualization & Alerting"
        GRAF["Grafana"]
        AM["Alertmanager"]
    end
    API --> PROM
    CEL --> PROM
    PROM --> GRAF
    PROM --> AM
    AM --> SLACK["Slack / PagerDuty"]
```

## Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `optimization_requests_total` | Counter | Total requests by status (success/error) |
| `optimization_duration_seconds` | Histogram | End-to-end latency |
| `quantum_solver_duration_seconds` | Histogram | Quantum solver execution time |
| `celery_task_queue_length` | Gauge | Queue depth by queue name |
| `cache_hit_ratio` | Gauge | Redis price cache hit rate |
| `active_websocket_connections` | Gauge | Current WebSocket connections |

## Cross-References

- **Operations runbook** → [Runbook](../17-operations/runbook.md)
- **Troubleshooting** → [Troubleshooting Guide](../17-operations/troubleshooting.md)
- **Health endpoints** → [Health Endpoint](../04-api-reference/health-endpoint.md)
- **Infrastructure** → [Docker Compose](../14-infrastructure/docker-compose.md)
- **CI/CD** → [CD Workflow](../15-cicd/cd-workflow.md)
