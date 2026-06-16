# Configuration Reference

This page is the authoritative reference for every configuration point in the Portfolio Optimizer. It covers application environment variables (read by `backend/app/core/config.py` via Pydantic Settings), Terraform infrastructure variables (`infra/terraform/variables.tf`), and Docker Compose environment variables.

## Application Environment Variables

The application reads configuration from environment variables (or a `.env` file in development). All variables are defined in `backend/app/core/config.py` as a Pydantic `BaseSettings` class, which provides type validation and default values.

```python
# backend/app/core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
```

> **Production note:** In ECS Fargate, environment variables are injected via the task definition. Sensitive values (passwords, API keys) are stored in AWS Secrets Manager and injected as `secrets` — never as plaintext environment variables.

### Database

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DATABASE_URL` | `str` | `postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer` | Async PostgreSQL DSN using the `asyncpg` driver. Must use the `postgresql+asyncpg://` scheme for SQLAlchemy async support. |

**Example values:**

```bash
# Local development
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer

# Docker Compose
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/portfolio_optimizer

# Production (ECS — injected from Secrets Manager)
DATABASE_URL=postgresql+asyncpg://portfolio_admin:${DB_PASSWORD}@rds-endpoint.us-east-1.rds.amazonaws.com:5432/portfolio_optimizer
```

### Redis

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `REDIS_URL` | `str` | `redis://localhost:6379/0` | Redis connection URL for the data cache (market price data). Uses database 0. |
| `CELERY_BROKER_URL` | `str` | `redis://localhost:6379/1` | Celery broker URL. Uses database 1 to isolate broker messages from cache data. |
| `CELERY_RESULT_BACKEND` | `str` | `redis://localhost:6379/2` | Celery result backend URL. Uses database 2. Task results expire after 24 hours (`result_expires=86400`). |

> **ElastiCache:** In production, all three Redis URLs point to the same ElastiCache endpoint but different database indices. The AUTH token is appended: `redis://:${REDIS_AUTH_TOKEN}@elasticache-endpoint:6379/0`.

### OpenAI

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENAI_API_KEY` | `str` | `""` (empty) | OpenAI API key for the GPT-4o LLM explanation node. If empty, the agent falls back to a template-based explanation. Starts with `sk-`. |

### Application

| Variable | Type | Default | Allowed Values | Description |
|----------|------|---------|----------------|-------------|
| `ENVIRONMENT` | `str` | `development` | `development`, `staging`, `production` | Runtime environment. Controls logging verbosity, error detail exposure, and feature flags. |
| `LOG_LEVEL` | `str` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Logging level for structured JSON logs. Use `DEBUG` only in development — it is very verbose. |

### Quantum Engine

| Variable | Type | Default | Constraints | Description |
|----------|------|---------|-------------|-------------|
| `QUANTUM_TIMEOUT_SECONDS` | `int` | `60` | `10 ≤ value ≤ 600` | Maximum wall-clock seconds for a single quantum optimization run (QAOA or VQE). When exceeded, Celery raises `SoftTimeLimitExceeded` and the run is marked `failed` with error code `QUANTUM_TIMEOUT`. The Celery soft limit is set to `QUANTUM_TIMEOUT_SECONDS + 60`; the hard kill limit is `QUANTUM_TIMEOUT_SECONDS + 120`. |
| `MAX_QUANTUM_ASSETS` | `int` | `8` | `2 ≤ value ≤ 20` | Maximum number of assets allowed in a quantum optimization request. QAOA/VQE complexity grows exponentially with asset count — 8 assets requires a 256-dimensional Hilbert space. Requests exceeding this limit receive a `QUANTUM_ASSET_LIMIT_EXCEEDED` error. |

### Data and Caching

| Variable | Type | Default | Constraints | Description |
|----------|------|---------|-------------|-------------|
| `CACHE_TTL_SECONDS` | `int` | `3600` | `≥ 60` | Redis TTL for cached market price data. After this period, the next request for the same tickers triggers a fresh yfinance fetch. Set lower (e.g., `300`) for more up-to-date data; set higher (e.g., `86400`) to reduce yfinance API calls. |

### Portfolio Metrics

| Variable | Type | Default | Constraints | Description |
|----------|------|---------|-------------|-------------|
| `RISK_FREE_RATE` | `float` | `0.02` | `0.0 ≤ value ≤ 0.2` | Annual risk-free rate used in Sharpe ratio calculations. Expressed as a decimal (e.g., `0.02` = 2%). Update this to match the current 3-month Treasury yield. |

### Complete `.env` Template

```bash
# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY=sk-your-key-here

# ── Application ───────────────────────────────────────────────────────────────
ENVIRONMENT=development
LOG_LEVEL=INFO

# ── Quantum Engine ────────────────────────────────────────────────────────────
QUANTUM_TIMEOUT_SECONDS=60
MAX_QUANTUM_ASSETS=8

# ── Data / Caching ────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS=3600

# ── Portfolio Metrics ─────────────────────────────────────────────────────────
RISK_FREE_RATE=0.02
```

### Docker Compose Environment Variables

The `docker-compose.yml` file defines two additional variables that control Celery worker concurrency. These are not part of the Pydantic `Settings` class — they are passed directly to the Celery worker command:

| Variable | Default | Description |
|----------|---------|-------------|
| `CELERY_DEFAULT_CONCURRENCY` | `4` | Number of concurrent worker processes for the `default` queue (classical optimization). Each process handles one task at a time (`worker_prefetch_multiplier=1`). |
| `CELERY_QUANTUM_CONCURRENCY` | `2` | Number of concurrent worker processes for the `quantum` queue. Lower than default because quantum simulations are CPU-intensive. |

```bash
# Override in shell before running docker-compose
export CELERY_DEFAULT_CONCURRENCY=8
export CELERY_QUANTUM_CONCURRENCY=2
docker-compose up -d
```

---

## Terraform Variables

Terraform variables are defined in `infra/terraform/variables.tf` and set via `terraform.tfvars` files or `-var` flags. Sensitive variables (passwords, API keys) are passed as `TF_VAR_*` environment variables in CI/CD.

### Project Identity

| Variable | Type | Default | Validation | Description |
|----------|------|---------|------------|-------------|
| `project_name` | `string` | `portfolio-optimizer` | 4–30 lowercase alphanumeric + hyphens, starts with letter | Short name used as a prefix for all AWS resource names. Changing this after initial deployment renames all resources. |
| `environment` | `string` | *(required)* | `development`, `staging`, `production` | Deployment environment. Combined with `project_name` to form the `name_prefix` local: `${project_name}-${environment}`. |
| `aws_region` | `string` | `us-east-1` | — | AWS region for all resources. Must match the region of your ACM certificate. |

### Networking

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `vpc_cidr` | `string` | `10.0.0.0/16` | CIDR block for the VPC. Provides 65,536 IP addresses. |
| `public_subnet_cidrs` | `list(string)` | `["10.0.1.0/24", "10.0.2.0/24"]` | CIDR blocks for public subnets (one per AZ). Hosts the ALB. |
| `private_subnet_cidrs` | `list(string)` | `["10.0.10.0/24", "10.0.11.0/24"]` | CIDR blocks for private subnets (one per AZ). Hosts ECS tasks, RDS, and ElastiCache. |
| `enable_nat_gateway` | `bool` | `true` | Whether to create NAT Gateway(s) for private subnet internet access (needed for ECR image pulls and yfinance API calls). |
| `single_nat_gateway` | `bool` | `false` | Use a single NAT Gateway to save cost. Set `true` for non-production; `false` for production HA. |

### Database (RDS PostgreSQL)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `db_name` | `string` | `portfolio_optimizer` | PostgreSQL database name. |
| `db_username` | `string` | `portfolio_admin` | PostgreSQL master username. |
| `db_password` | `string` | *(sensitive, required)* | PostgreSQL master password. Stored in AWS Secrets Manager. Pass via `TF_VAR_db_password`. |
| `db_instance_class` | `string` | `db.t3.medium` | RDS instance class. `db.t3.medium` provides 2 vCPU and 4 GiB RAM. For higher throughput, use `db.r6g.large` or larger. |
| `db_allocated_storage` | `number` | `20` | Initial allocated storage in GiB. RDS auto-scales storage up to 1000 GiB by default. |
| `db_multi_az` | `bool` | `true` | Enable Multi-AZ standby replica for automatic failover. Strongly recommended for production. Doubles the RDS cost. |
| `db_deletion_protection` | `bool` | `true` | Prevent accidental deletion of the RDS instance. Must be disabled before `terraform destroy`. |
| `db_backup_retention_days` | `number` | `7` | Number of days to retain automated RDS backups. Maximum is 35. |

### ElastiCache Redis

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `redis_node_type` | `string` | `cache.t3.micro` | ElastiCache node type. `cache.t3.micro` provides 0.5 GiB RAM. For production with many concurrent users, use `cache.r6g.large` (13 GiB). |
| `redis_num_cache_nodes` | `number` | `1` | Number of cache nodes. For production HA, use a replication group with `redis_num_cache_nodes=2`. |
| `redis_auth_token` | `string` | *(sensitive, required)* | Redis AUTH token. Minimum 16 characters. Stored in AWS Secrets Manager. |

### ALB / DNS / TLS

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `acm_certificate_arn` | `string` | `""` (empty) | ARN of the ACM certificate for HTTPS on the ALB. If empty, the HTTPS listener is skipped and only HTTP (port 80) is configured. Must be in the same region as the ALB. |
| `domain_name` | `string` | `""` (empty) | Primary domain name (e.g., `portfolio-optimizer.example.com`). Used in the `application_url` output and passed to ECS tasks as an environment variable. |

### ECS Task Sizing

CPU units: 1024 = 1 vCPU. Memory in MiB.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `backend_cpu` | `number` | `1024` | CPU units for the FastAPI backend Fargate task (1 vCPU). |
| `backend_memory` | `number` | `2048` | Memory (MiB) for the backend task (2 GiB). |
| `worker_cpu` | `number` | `2048` | CPU units for the Celery worker Fargate task (2 vCPU). Workers are CPU-intensive due to quantum simulation. |
| `worker_memory` | `number` | `4096` | Memory (MiB) for the worker task (4 GiB). Quantum simulations require significant memory for state vectors. |
| `frontend_cpu` | `number` | `256` | CPU units for the Nginx frontend task (0.25 vCPU). |
| `frontend_memory` | `number` | `512` | Memory (MiB) for the frontend task (0.5 GiB). |

### ECS Desired Counts and Auto-Scaling

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `backend_desired_count` | `number` | `2` | Initial desired number of backend task replicas. |
| `worker_desired_count` | `number` | `2` | Initial desired number of Celery worker task replicas. |
| `frontend_desired_count` | `number` | `2` | Initial desired number of frontend task replicas. |
| `backend_min_capacity` | `number` | `2` | Minimum backend tasks for auto-scaling. Never scales below this. |
| `backend_max_capacity` | `number` | `10` | Maximum backend tasks for auto-scaling. |
| `worker_min_capacity` | `number` | `1` | Minimum worker tasks for auto-scaling. |
| `worker_max_capacity` | `number` | `8` | Maximum worker tasks for auto-scaling. |

### Application Config (passed to ECS tasks)

These Terraform variables are passed through to ECS task environment variables:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `log_level` | `string` | `INFO` | Application log level. Validated: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `quantum_timeout_seconds` | `number` | `60` | Maps to `QUANTUM_TIMEOUT_SECONDS` env var in ECS tasks. |
| `max_quantum_assets` | `number` | `8` | Maps to `MAX_QUANTUM_ASSETS` env var in ECS tasks. |
| `cache_ttl_seconds` | `number` | `3600` | Maps to `CACHE_TTL_SECONDS` env var in ECS tasks. |
| `risk_free_rate` | `number` | `0.02` | Maps to `RISK_FREE_RATE` env var in ECS tasks. |

### CloudWatch

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `cloudwatch_log_retention_days` | `number` | `30` | Days to retain CloudWatch log groups for all services. |
| `alarm_sns_topic_arn` | `string` | `""` (empty) | SNS topic ARN for CloudWatch alarm notifications. If empty, alarms are created but no notifications are sent. |

### ECR

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ecr_image_retention_count` | `number` | `10` | Number of images to retain in each ECR repository. Older images are automatically deleted. |
| `backend_image_tag` | `string` | `latest` | Docker image tag for the backend service. Overridden by the CD workflow with the Git SHA. |
| `worker_image_tag` | `string` | `latest` | Docker image tag for the worker service. |
| `frontend_image_tag` | `string` | `latest` | Docker image tag for the frontend service. |

### Sensitive Variables (passed via `TF_VAR_*`)

| Variable | Description | How to Set |
|----------|-------------|------------|
| `openai_api_key` | OpenAI API key | `export TF_VAR_openai_api_key="sk-..."` |
| `db_password` | PostgreSQL master password | `export TF_VAR_db_password="$(openssl rand -base64 32)"` |
| `redis_auth_token` | Redis AUTH token | `export TF_VAR_redis_auth_token="$(openssl rand -hex 32)"` |

---

## Example `terraform.tfvars`

```hcl
# infra/terraform/environments/production/terraform.tfvars

project_name = "portfolio-optimizer"
environment  = "production"
aws_region   = "us-east-1"

# Networking
vpc_cidr            = "10.0.0.0/16"
single_nat_gateway  = false   # HA: one NAT per AZ

# Database
db_instance_class        = "db.t3.medium"
db_allocated_storage     = 20
db_multi_az              = true
db_deletion_protection   = true
db_backup_retention_days = 7

# ElastiCache
redis_node_type       = "cache.t3.micro"
redis_num_cache_nodes = 1

# DNS / TLS
acm_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/..."
domain_name         = "portfolio-optimizer.example.com"

# ECS Task Sizing
backend_cpu    = 1024
backend_memory = 2048
worker_cpu     = 2048
worker_memory  = 4096
frontend_cpu   = 256
frontend_memory = 512

# ECS Counts
backend_desired_count  = 2
worker_desired_count   = 2
frontend_desired_count = 2

# Auto-scaling
backend_min_capacity = 2
backend_max_capacity = 10
worker_min_capacity  = 1
worker_max_capacity  = 8

# Application
log_level               = "INFO"
quantum_timeout_seconds = 60
max_quantum_assets      = 8
cache_ttl_seconds       = 3600
risk_free_rate          = 0.02

# CloudWatch
cloudwatch_log_retention_days = 30
```

---

## Configuration Relationships

```mermaid
graph TD
    A["terraform.tfvars<br/>(Terraform variables)"] --> B["ECS Task Definition<br/>(environment vars)"]
    B --> C["Settings class<br/>(Pydantic BaseSettings)"]
    D[".env file<br/>(local dev only)"] --> C
    E["AWS Secrets Manager<br/>(passwords, API keys)"] --> B
    C --> F["Application Runtime"]
    F --> G["QUANTUM_TIMEOUT_SECONDS<br/>→ Celery soft_time_limit"]
    F --> H["CACHE_TTL_SECONDS<br/>→ Redis TTL"]
    F --> I["MAX_QUANTUM_ASSETS<br/>→ Request validation"]
    F --> J["RISK_FREE_RATE<br/>→ Sharpe ratio calc"]
```

---

## Related Pages

- [Backend Configuration](../03-backend/configuration.md) — Pydantic Settings deep dive
- [Deployment Guide](deployment-guide.md) — how to apply these configurations
- [GitHub Secrets & Variables](../15-cicd/github-secrets.md) — CI/CD configuration
- [Terraform Overview](../14-infrastructure/terraform-overview.md) — infrastructure modules
- [Troubleshooting](troubleshooting.md) — configuration-related issues
