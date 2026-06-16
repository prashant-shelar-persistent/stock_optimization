# Troubleshooting

This page covers the most common operational issues encountered in the Portfolio Optimizer, their root causes, diagnostic steps, and remediation procedures. Issues are organized by component.

---

## Quantum Optimization Issues

### Quantum Job Timeout (`QUANTUM_TIMEOUT`)

**Symptom:** Optimization runs with `include_quantum: true` fail with error code `QUANTUM_TIMEOUT`. The run status transitions to `failed` with message: *"Quantum optimization timed out. Try reducing the number of assets or disabling quantum optimization."*

**Root cause:** QAOA and VQE are variational algorithms whose runtime grows exponentially with the number of assets. The Celery worker enforces a `SoftTimeLimitExceeded` after `QUANTUM_TIMEOUT_SECONDS` (default: 60 seconds). With 8 assets, a QAOA circuit has 256 basis states; each additional asset doubles the state space.

**Diagnostic steps:**

```bash
# Check the run's error details via the API
curl -s "https://your-domain/api/v1/runs/{run_id}" | jq '.error_message, .error_code'

# Check Celery worker logs for the timeout event
aws logs filter-log-events \
  --log-group-name /portfolio-optimizer/production/worker \
  --filter-pattern "QUANTUM_TIMEOUT OR SoftTimeLimitExceeded" \
  --start-time $(date -d '1 hour ago' +%s000)
```

**Remediation options:**

1. **Increase `QUANTUM_TIMEOUT_SECONDS`** — suitable if the job is close to completing:

   ```bash
   # In terraform.tfvars
   quantum_timeout_seconds = 120   # increase from 60 to 120

   # Or set directly in ECS task definition environment
   # Then redeploy: gh workflow run cd.yml --field environment=production
   ```

   > **Constraint:** Maximum allowed value is 600 seconds (10 minutes). The Celery task hard kill limit is `QUANTUM_TIMEOUT_SECONDS + 120`.

2. **Reduce the number of assets** — the most effective solution. Quantum optimization is limited to `MAX_QUANTUM_ASSETS` (default: 8). Reducing to 5–6 assets dramatically cuts runtime:

   ```json
   {
     "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"],
     "include_quantum": true
   }
   ```

3. **Disable quantum optimization** — use classical MVO only:

   ```json
   {
     "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX"],
     "include_quantum": false
   }
   ```

4. **Increase worker CPU** — quantum simulations are CPU-bound. Upgrading the Fargate task from 2 vCPU to 4 vCPU can reduce runtime by ~40%:

   ```hcl
   # terraform.tfvars
   worker_cpu    = 4096   # 4 vCPU
   worker_memory = 8192   # 8 GiB
   ```

---

### Quantum Asset Limit Exceeded (`QUANTUM_ASSET_LIMIT_EXCEEDED`)

**Symptom:** Request returns HTTP 422 with error code `QUANTUM_ASSET_LIMIT_EXCEEDED`.

**Root cause:** The request includes more tickers than `MAX_QUANTUM_ASSETS` (default: 8) with `include_quantum: true`.

**Remediation:** Either reduce the ticker list or increase `MAX_QUANTUM_ASSETS` (up to 20, but expect very long runtimes above 10 assets):

```bash
# Increase the limit (use with caution)
# In terraform.tfvars:
max_quantum_assets = 10
```

---

## Data Fetch Issues

### `DATA_FETCH_ERROR` — yfinance Rate Limiting

**Symptom:** Optimization runs fail with error code `DATA_FETCH_ERROR`. The error message mentions "Empty DataFrame" or "Network timeout". This often occurs in bursts when many users submit requests simultaneously.

**Root cause:** yfinance fetches data from Yahoo Finance's unofficial API. Yahoo Finance enforces rate limits that are not publicly documented. When multiple workers fetch data for the same or different tickers simultaneously, requests may be throttled or rejected.

**Diagnostic steps:**

```bash
# Check worker logs for yfinance errors
aws logs filter-log-events \
  --log-group-name /portfolio-optimizer/production/worker \
  --filter-pattern "DATA_FETCH_ERROR OR yfinance OR rate" \
  --start-time $(date -d '30 minutes ago' +%s000) \
  | jq '.events[].message'

# Check Redis cache hit rate (low hit rate = more yfinance calls)
redis-cli -h your-elasticache-endpoint INFO stats | grep keyspace_hits
```

**Remediation:**

1. **Check Redis cache health** — if the cache is empty or evicting keys, every request hits yfinance:

   ```bash
   # Connect to Redis and check cache keys
   redis-cli -h your-elasticache-endpoint -a "$REDIS_AUTH_TOKEN"
   
   # Check number of cached market data keys
   KEYS market_data:*
   
   # Check memory usage
   INFO memory
   ```

2. **Increase `CACHE_TTL_SECONDS`** — longer TTL means fewer yfinance calls:

   ```bash
   # In terraform.tfvars or environment variable
   cache_ttl_seconds = 7200   # 2 hours instead of 1
   ```

3. **Flush and repopulate the cache** — if the cache contains stale or corrupted entries:

   ```bash
   # Flush only market data keys (not Celery broker/results)
   redis-cli -h your-elasticache-endpoint -a "$REDIS_AUTH_TOKEN" \
     --scan --pattern "market_data:*" | xargs redis-cli DEL
   ```

4. **Retry the request** — yfinance rate limiting is transient. The Celery task automatically retries up to 3 times with exponential backoff (30s, 60s, 120s). If the error persists after retries, wait 5–10 minutes before resubmitting.

5. **Check yfinance version** — outdated versions may have broken API compatibility:

   ```bash
   # Check installed version in the worker container
   aws ecs execute-command \
     --cluster portfolio-optimizer-production-cluster \
     --task <task-id> \
     --container worker \
     --interactive \
     --command "pip show yfinance"
   ```

---

### `DATA_FETCH_ERROR` — Invalid Tickers

**Symptom:** `DATA_FETCH_ERROR` with message mentioning specific tickers that returned no data.

**Root cause:** The requested ticker symbols are invalid, delisted, or not available on Yahoo Finance.

**Diagnostic steps:**

```bash
# The error details include the problematic tickers
curl -s "https://your-domain/api/v1/runs/{run_id}" | jq '.error_details'
# Returns: {"tickers": ["INVALID_TICKER", "DELISTED_STOCK"]}
```

**Remediation:** Remove invalid tickers from the request. Use the `/api/v1/assets` endpoint to validate tickers before submitting an optimization:

```bash
curl "https://your-domain/api/v1/assets?tickers=AAPL,MSFT,INVALID" | jq '.valid_tickers'
```

---

## Optimization Solver Issues

### `SOLVER_INFEASIBLE` — Conflicting Constraints

**Symptom:** Optimization runs fail with error code `SOLVER_INFEASIBLE`. The error message includes `relaxation_suggestions` listing which constraints to relax.

**Root cause:** The CVXPY solver (SCS or ECOS) cannot find a portfolio that satisfies all constraints simultaneously. Common causes:

| Conflicting Constraints | Example |
|------------------------|---------|
| `min_portfolio_return` too high | Requiring 50% annual return when no asset achieves it |
| `max_weight_per_asset` too low | Setting 5% max weight with 25 assets (sum = 125% > 100%) |
| Sector limits too restrictive | Technology cap of 10% when 80% of assets are tech stocks |
| `min_weight_per_asset` + `max_weight_per_asset` conflict | min=10%, max=5% |

**Diagnostic steps:**

```bash
# Get the full error details including relaxation suggestions
curl -s "https://your-domain/api/v1/runs/{run_id}" | jq '{
  error_code: .error_code,
  message: .error_message,
  suggestions: .error_details.relaxation_suggestions
}'
```

**Remediation:**

1. **Follow the relaxation suggestions** — the API returns specific suggestions:

   ```json
   {
     "relaxation_suggestions": [
       "Reduce min_portfolio_return from 0.25 to below 0.15",
       "Increase max_weight_per_asset from 0.05 to at least 0.10",
       "Remove sector_constraints for Technology"
     ]
   }
   ```

2. **Common fixes:**

   ```json
   // Before (infeasible)
   {
     "constraints": {
       "min_portfolio_return": 0.30,
       "max_weight_per_asset": 0.05,
       "sector_constraints": {"Technology": 0.10}
     }
   }

   // After (feasible)
   {
     "constraints": {
       "min_portfolio_return": 0.12,
       "max_weight_per_asset": 0.20,
       "sector_constraints": {"Technology": 0.40}
     }
   }
   ```

3. **Remove all constraints** to verify the base optimization works, then add constraints back one at a time.

---

## WebSocket Issues

### WebSocket Connection Drops

**Symptom:** The frontend loses the WebSocket connection during a long-running optimization (typically quantum jobs taking 60+ seconds). The progress stream stops and the UI shows a disconnected state.

**Root cause:** Load balancers and reverse proxies enforce idle connection timeouts. AWS ALB has a default idle timeout of 60 seconds. If no data is sent over the WebSocket for 60 seconds, the ALB closes the connection.

The WebSocket handler sends keepalive pings every 30 seconds to prevent this:

```python
# backend/app/api/websocket.py
# Keepalive ping sent every 30 seconds
{"type": "ping", "run_id": "..."}
```

If pings are not reaching the client, the connection may still drop.

**Diagnostic steps:**

```bash
# Check ALB idle timeout setting
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn <alb-arn> \
  --query 'Attributes[?Key==`idle_timeout.timeout_seconds`]'

# Check for WebSocket-related errors in backend logs
aws logs filter-log-events \
  --log-group-name /portfolio-optimizer/production/backend \
  --filter-pattern "WebSocketDisconnect OR websocket" \
  --start-time $(date -d '1 hour ago' +%s000)
```

**Remediation:**

1. **Increase ALB idle timeout** — set to 300 seconds (5 minutes) to accommodate long quantum jobs:

   ```hcl
   # In infra/terraform/modules/alb/main.tf
   resource "aws_lb" "main" {
     idle_timeout = 300
   }
   ```

   Or via AWS CLI:
   ```bash
   aws elbv2 modify-load-balancer-attributes \
     --load-balancer-arn <alb-arn> \
     --attributes Key=idle_timeout.timeout_seconds,Value=300
   ```

2. **Verify keepalive is working** — the WebSocket handler sends pings every 30 seconds. If the frontend is not receiving them, check for proxy buffering:

   ```bash
   # Check if Nginx (frontend) is buffering WebSocket traffic
   # Nginx should have: proxy_read_timeout 300s; proxy_buffering off;
   ```

3. **Frontend reconnection** — the frontend should implement automatic reconnection with exponential backoff. If it doesn't, users can manually refresh the page and check the run status via the `/api/v1/runs/{run_id}` endpoint.

---

## Celery Worker Issues

### Worker Not Picking Up Tasks

**Symptom:** Optimization runs stay in `pending` status indefinitely. The Celery worker is running but not processing tasks.

**Root cause:** The worker cannot connect to the Redis broker, or the worker is consuming the wrong queue.

**Diagnostic steps:**

```bash
# Check if the worker is connected to Redis
aws logs filter-log-events \
  --log-group-name /portfolio-optimizer/production/worker \
  --filter-pattern "celery_worker_ready OR ConnectionError OR broker" \
  --start-time $(date -d '30 minutes ago' +%s000)

# Check Redis broker connectivity from within the worker container
aws ecs execute-command \
  --cluster portfolio-optimizer-production-cluster \
  --task <worker-task-id> \
  --container worker \
  --interactive \
  --command "redis-cli -h $REDIS_HOST ping"

# Check the Celery queue depth
redis-cli -h your-elasticache-endpoint -a "$REDIS_AUTH_TOKEN" \
  LLEN celery   # default queue
redis-cli -h your-elasticache-endpoint -a "$REDIS_AUTH_TOKEN" \
  LLEN quantum  # quantum queue
```

**Remediation:**

1. **Verify Redis broker URL** — the worker must use `CELERY_BROKER_URL` (database 1), not `REDIS_URL` (database 0):

   ```bash
   # Check the ECS task definition environment variables
   aws ecs describe-task-definition \
     --task-definition portfolio-optimizer-production-worker \
     --query 'taskDefinition.containerDefinitions[0].environment'
   ```

2. **Restart the worker service** — force a new deployment to restart all worker tasks:

   ```bash
   aws ecs update-service \
     --cluster portfolio-optimizer-production-cluster \
     --service portfolio-optimizer-production-worker \
     --force-new-deployment
   ```

3. **Check queue routing** — quantum jobs must go to the `quantum` queue, which is consumed by the quantum worker. Classical jobs go to the `default` queue:

   ```bash
   # Verify the worker is consuming the correct queue
   aws logs filter-log-events \
     --log-group-name /portfolio-optimizer/production/worker \
     --filter-pattern "queues" \
     --start-time $(date -d '1 hour ago' +%s000)
   # Should show: "queues": ["quantum", "default"] or ["default"]
   ```

4. **Check for stuck tasks** — if a task is stuck in `STARTED` state, the worker may have crashed mid-task. With `task_acks_late=True` and `task_reject_on_worker_lost=True`, the task should be re-queued automatically when the worker restarts.

---

### Worker Memory Exhaustion

**Symptom:** Worker tasks fail with `MemoryError` or the ECS task is killed by the OOM killer. CloudWatch shows `MemoryUtilization` at 100%.

**Root cause:** Quantum simulations (especially VQE with many assets) require large state vectors. The default 4 GiB worker memory may be insufficient for 8-asset quantum runs.

**Remediation:**

```hcl
# Increase worker memory in terraform.tfvars
worker_cpu    = 4096   # 4 vCPU
worker_memory = 8192   # 8 GiB
```

Also consider reducing `MAX_QUANTUM_ASSETS` to limit the maximum state vector size.

---

## Database Migration Failures

### `alembic upgrade head` Fails

**Symptom:** The CD workflow's `run-migrations` job fails. The ECS migration task exits with a non-zero code.

**Diagnostic steps:**

```bash
# Get the migration task ARN from the CD workflow logs
# Then check the task logs
aws logs filter-log-events \
  --log-group-name /portfolio-optimizer/production/backend \
  --filter-pattern "alembic OR migration OR ERROR" \
  --start-time $(date -d '30 minutes ago' +%s000) \
  | jq '.events[].message'
```

**Common failure modes:**

#### 1. Database connection refused

```
sqlalchemy.exc.OperationalError: (asyncpg.exceptions.ConnectionRefusedError)
```

**Cause:** The migration task cannot reach the RDS instance. Check security group rules — the backend security group must allow outbound TCP 5432 to the RDS security group.

```bash
# Check security group rules
aws ec2 describe-security-groups \
  --group-ids <backend-sg-id> \
  --query 'SecurityGroups[0].IpPermissionsEgress'
```

#### 2. Authentication failure

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed
```

**Cause:** The `DATABASE_URL` environment variable contains an incorrect password. Verify the Secrets Manager secret matches the RDS password.

```bash
# Check the secret value (requires appropriate IAM permissions)
aws secretsmanager get-secret-value \
  --secret-id portfolio-optimizer-production-db-password \
  --query SecretString
```

#### 3. Migration conflict

```
alembic.util.exc.CommandError: Can't locate revision identified by 'abc123'
```

**Cause:** The migration history in the database is out of sync with the migration files. This can happen if migrations were applied manually or if a migration file was deleted.

**Remediation:**

```bash
# Run an interactive migration task to inspect the state
aws ecs run-task \
  --cluster portfolio-optimizer-production-cluster \
  --task-definition portfolio-optimizer-production-backend \
  --launch-type FARGATE \
  --network-configuration "..." \
  --overrides '{
    "containerOverrides": [{
      "name": "backend",
      "command": ["alembic", "history", "--verbose"]
    }]
  }'

# Check current revision
aws ecs run-task ... \
  --overrides '{
    "containerOverrides": [{
      "name": "backend",
      "command": ["alembic", "current"]
    }]
  }'
```

#### 4. Schema conflict (column already exists)

```
asyncpg.exceptions.DuplicateColumnError: column "new_column" of relation "optimization_runs" already exists
```

**Cause:** A migration was applied manually to the database but not recorded in the `alembic_version` table.

**Remediation:** Stamp the database with the correct revision without running the migration:

```bash
# Stamp the database at the current head (use with caution)
aws ecs run-task ... \
  --overrides '{
    "containerOverrides": [{
      "name": "backend",
      "command": ["alembic", "stamp", "head"]
    }]
  }'
```

> **Warning:** Only use `alembic stamp` if you are certain the schema is already at the target revision. Incorrect stamping can cause future migrations to fail or skip necessary changes.

---

## Health Check Failures

### Service Fails Health Checks After Deployment

**Symptom:** New ECS tasks start but fail their health checks. The ALB shows targets as `unhealthy`. The service rolls back to the previous task definition.

**Diagnostic steps:**

```bash
# Check ALB target health
aws elbv2 describe-target-health \
  --target-group-arn <backend-target-group-arn> \
  --query 'TargetHealthDescriptions[*].{Target:Target.Id,Health:TargetHealth.State,Reason:TargetHealth.Reason}'

# Check backend startup logs
aws logs filter-log-events \
  --log-group-name /portfolio-optimizer/production/backend \
  --filter-pattern "ERROR OR startup OR health" \
  --start-time $(date -d '15 minutes ago' +%s000)
```

**Common causes:**

| Cause | Symptom in Logs | Fix |
|-------|----------------|-----|
| Database migration failed | `OperationalError` during startup | Fix migration, redeploy |
| Missing environment variable | `ValidationError` from Pydantic | Check ECS task definition env vars |
| Port mismatch | `Connection refused` on health check | Verify container port = 8000 |
| Slow startup | Health check timeout before app ready | Increase `start_period` in health check |

---

## Observability Quick Reference

When diagnosing issues, these CloudWatch log groups and metrics are most useful:

| Resource | Location | Use For |
|----------|----------|---------|
| Backend logs | `/portfolio-optimizer/production/backend` | API errors, startup failures |
| Worker logs | `/portfolio-optimizer/production/worker` | Task failures, timeouts |
| Frontend logs | `/portfolio-optimizer/production/frontend` | Nginx errors |
| ECS CPU metric | `AWS/ECS` → `CPUUtilization` | Worker overload |
| ECS Memory metric | `AWS/ECS` → `MemoryUtilization` | OOM issues |
| ALB 5xx errors | `AWS/ApplicationELB` → `HTTPCode_Target_5XX_Count` | Backend errors |
| RDS connections | `AWS/RDS` → `DatabaseConnections` | Connection pool exhaustion |

For Grafana dashboards and alert configurations, see [Observability](../16-observability/grafana-dashboards.md).

---

## Related Pages

- [Runbook](runbook.md) — operational procedures for scaling, backup, and recovery
- [Configuration Reference](configuration-reference.md) — all configuration variables
- [Deployment Guide](deployment-guide.md) — deployment procedures
- [Error Codes](../04-api-reference/error-codes.md) — complete API error code reference
- [Celery Configuration](../10-task-queue/celery-configuration.md) — task queue details
- [Quantum Dispatcher](../07-quantum-optimization/quantum-dispatcher.md) — quantum routing logic
