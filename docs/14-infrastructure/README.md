# Infrastructure

Docker Compose, Terraform IaC, and AWS architecture documentation for the Portfolio Optimizer.

## Section Contents

| Page | Description |
|------|-------------|
| [Docker Compose](docker-compose.md) | Service definitions, networking, volumes, and health checks |
| [Terraform Overview](terraform-overview.md) | IaC structure, state management, and workspace organization |
| [Terraform Modules](terraform-modules.md) | ECS, RDS, ElastiCache, VPC, and ALB module documentation |
| [AWS Architecture](aws-architecture.md) | VPC topology, ECS Fargate services, RDS, and ALB configuration |
| [Environments](environments.md) | dev / staging / prod environment configuration and promotion |

## Infrastructure Overview

```mermaid
graph TD
    subgraph "AWS VPC"
        subgraph "Public Subnets (2 AZs)"
            ALB["Application Load Balancer<br/>(HTTPS · TLS termination)"]
        end
        subgraph "Private Subnets (2 AZs)"
            ECS_API["ECS Fargate<br/>FastAPI Service"]
            ECS_CEL["ECS Fargate<br/>Celery Workers"]
            RDS["RDS PostgreSQL 16<br/>(Multi-AZ)"]
            EC["ElastiCache Redis<br/>(cluster mode)"]
        end
    end
    ECR["ECR<br/>(Docker images)"]
    SM["Secrets Manager<br/>(credentials)"]
    Internet --> ALB --> ECS_API
    ECS_API --> RDS
    ECS_API --> EC
    ECS_CEL --> RDS
    ECS_CEL --> EC
    ECS_API --> ECR
    ECS_API --> SM
```

## Environments

| Environment | Purpose | Terraform Workspace |
|-------------|---------|-------------------|
| `dev` | Development and testing | `dev` |
| `staging` | Pre-production validation | `staging` |
| `prod` | Production | `prod` |

## Cross-References

- **CI/CD pipelines** → [CI Workflow](../15-cicd/ci-workflow.md) · [CD Workflow](../15-cicd/cd-workflow.md)
- **Terraform workflow** → [Terraform Workflow](../15-cicd/terraform-workflow.md)
- **Operations** → [Deployment Guide](../17-operations/deployment-guide.md)
- **Observability** → [Prometheus Metrics](../16-observability/prometheus-metrics.md)
