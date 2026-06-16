# GitHub Secrets & Variables

This page documents every GitHub Actions secret and variable required by the Portfolio Optimizer CI/CD pipelines. Secrets store sensitive values (credentials, API keys, passwords) that are masked in logs. Variables store non-sensitive configuration values that are visible in workflow logs.

## Overview

GitHub Actions provides two types of repository-level configuration:

| Type | Visibility | Use For |
|------|-----------|---------|
| **Secrets** | Masked in logs, never exposed | Passwords, API keys, private ARNs |
| **Variables** | Visible in logs | Region names, cluster names, URLs |

Both can be scoped to:
- **Repository** — available to all workflows in the repo
- **Environment** — available only when a workflow targets a specific environment (e.g., `staging`, `production`)

> **Best practice:** Use environment-scoped secrets and variables for anything that differs between staging and production (e.g., `STAGING_ALB_URL` vs `PRODUCTION_ALB_URL`). Use repository-scoped secrets for values shared across environments (e.g., `AWS_ACCOUNT_ID`).

## How to Set Secrets and Variables

### Via GitHub Web UI

1. Navigate to your repository on GitHub
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** or **New repository variable**
4. Enter the name and value, then click **Add secret** / **Add variable**

For environment-scoped values:
1. Go to **Settings** → **Environments**
2. Create or select an environment (e.g., `staging`, `production`)
3. Under **Environment secrets** or **Environment variables**, add the value

### Via GitHub CLI

```bash
# Set a repository secret
gh secret set AWS_ACCOUNT_ID --body "123456789012"

# Set a repository variable
gh variable set AWS_REGION --body "us-east-1"

# Set an environment secret
gh secret set DB_PASSWORD \
  --env production \
  --body "$(openssl rand -base64 32)"

# Set an environment variable
gh variable set PRODUCTION_ALB_URL \
  --env production \
  --body "portfolio-optimizer-prod-alb-1234567890.us-east-1.elb.amazonaws.com"
```

### Via Terraform Bootstrap Outputs

After running the bootstrap module, capture the outputs and set them as GitHub variables:

```bash
cd infra/terraform/bootstrap

# Get outputs
TF_STATE_BUCKET=$(terraform output -raw state_bucket_name)
TF_STATE_LOCK_TABLE=$(terraform output -raw state_lock_table_name)
AWS_ROLE_ARN=$(terraform output -raw github_actions_role_arn)

# Set as GitHub variables/secrets
gh variable set TF_STATE_BUCKET --body "$TF_STATE_BUCKET"
gh variable set TF_STATE_LOCK_TABLE --body "$TF_STATE_LOCK_TABLE"
gh secret set AWS_ROLE_ARN --body "$AWS_ROLE_ARN"
```

## Complete Reference

### AWS Identity

| Name | Type | Scope | Description | Example |
|------|------|-------|-------------|---------|
| `AWS_ACCOUNT_ID` | Variable | Repository | 12-digit AWS account ID | `123456789012` |
| `AWS_REGION` | Variable | Repository | AWS region for all resources | `us-east-1` |
| `AWS_DEPLOY_ROLE_ARN` | Variable | Repository | IAM role ARN for CD deployments (ECS updates, ECR push) | `arn:aws:iam::123456789012:role/portfolio-optimizer-github-actions-role` |
| `AWS_ROLE_ARN` | Secret | Repository | IAM role ARN for Terraform (broader permissions) | `arn:aws:iam::123456789012:role/portfolio-optimizer-github-actions-role` |

> **Note:** `AWS_DEPLOY_ROLE_ARN` and `AWS_ROLE_ARN` may point to the same IAM role if you use a single role for both CD and Terraform. Separating them allows you to apply least-privilege by giving the deploy role only ECS/ECR permissions and the Terraform role full provisioning permissions.

### Load Balancer URLs

| Name | Type | Scope | Description | Example |
|------|------|-------|-------------|---------|
| `PRODUCTION_ALB_URL` | Variable | Repository or `production` env | Production ALB DNS name (used for smoke tests) | `portfolio-optimizer-prod-1234567890.us-east-1.elb.amazonaws.com` |
| `STAGING_ALB_URL` | Variable | Repository or `staging` env | Staging ALB DNS name | `portfolio-optimizer-staging-0987654321.us-east-1.elb.amazonaws.com` |

These are the raw ALB DNS names output by Terraform (`infra/terraform/outputs.tf`). If you use a custom domain, you can use the domain name instead (e.g., `api.portfolio-optimizer.example.com`).

### ECS Configuration

| Name | Type | Scope | Description | Example |
|------|------|-------|-------------|---------|
| `ECS_CLUSTER_NAME` | Variable | Repository | ECS cluster name | `portfolio-optimizer-production-cluster` |
| `ECS_BACKEND_SERVICE` | Variable | Repository | Backend ECS service name | `portfolio-optimizer-production-backend` |
| `ECS_WORKER_SERVICE` | Variable | Repository | Celery worker ECS service name | `portfolio-optimizer-production-worker` |
| `ECS_FRONTEND_SERVICE` | Variable | Repository | Frontend ECS service name | `portfolio-optimizer-production-frontend` |
| `ECS_MIGRATION_TASK_DEF` | Variable | Repository | Task definition for Alembic migrations | `portfolio-optimizer-production-backend` |
| `ECS_SUBNET_IDS` | Variable | Repository | Comma-separated private subnet IDs for migration tasks | `subnet-0abc1234,subnet-0def5678` |
| `ECS_SECURITY_GROUP_ID` | Variable | Repository | Security group ID for migration tasks | `sg-0abc1234def56789` |

The ECS resource names follow the pattern `{project_name}-{environment}-{service}` as defined in `infra/terraform/main.tf`:

```hcl
locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
# Results in: portfolio-optimizer-production-backend
```

> **Tip:** After running `terraform apply`, retrieve these values from Terraform outputs:
> ```bash
> terraform output ecs_cluster_name
> terraform output ecs_backend_service_name
> terraform output ecs_worker_service_name
> terraform output ecs_frontend_service_name
> ```

### ECR Registry

| Name | Type | Scope | Description | Example |
|------|------|-------|-------------|---------|
| `ECR_REGISTRY` | Variable | Repository | ECR registry URL (without repository name) | `123456789012.dkr.ecr.us-east-1.amazonaws.com` |

The ECR registry URL follows the format `{account_id}.dkr.ecr.{region}.amazonaws.com`. Individual repository URLs are constructed as `{ECR_REGISTRY}/portfolio-optimizer-{service}:{tag}`.

### Terraform State Backend

| Name | Type | Scope | Description | Example |
|------|------|-------|-------------|---------|
| `TF_STATE_BUCKET` | Variable | Repository | S3 bucket name for Terraform state | `portfolio-optimizer-terraform-state-a1b2c3d4` |
| `TF_STATE_LOCK_TABLE` | Variable | Repository | DynamoDB table name for state locking | `portfolio-optimizer-terraform-state-lock` |

These are created by the bootstrap module at `infra/terraform/bootstrap/main.tf`. The S3 bucket name includes a random suffix to ensure global uniqueness.

### Application Secrets

| Name | Type | Scope | Description | Notes |
|------|------|-------|-------------|-------|
| `OPENAI_API_KEY` | Secret | Repository | OpenAI API key for LLM explanations | Starts with `sk-`. Stored in AWS Secrets Manager at runtime. |
| `DB_PASSWORD` | Secret | Repository | PostgreSQL master password | Use a strong random password (32+ chars). Stored in AWS Secrets Manager. |
| `REDIS_AUTH_TOKEN` | Secret | Repository | Redis AUTH token for ElastiCache | Minimum 16 characters. Stored in AWS Secrets Manager. |

These secrets are passed to Terraform as `TF_VAR_*` environment variables and stored in AWS Secrets Manager by the `secrets` module (`infra/terraform/modules/secrets/`). ECS tasks retrieve them at runtime via the task execution role.

> **Security:** These secrets are never baked into Docker images or stored in environment variables on the ECS task definition in plaintext. They are injected as `secrets` in the ECS task definition, which fetches them from Secrets Manager at container startup.

### DNS and TLS

| Name | Type | Scope | Description | Example |
|------|------|-------|-------------|---------|
| `ACM_CERTIFICATE_ARN` | Variable | Repository | ARN of the ACM certificate for HTTPS | `arn:aws:acm:us-east-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `DOMAIN_NAME` | Variable | Repository | Primary domain name for the application | `portfolio-optimizer.example.com` |

The ACM certificate must be in the same region as the ALB and must cover the `DOMAIN_NAME`. Create it in the AWS Certificate Manager console or via Terraform before running the infrastructure workflow.

### Monitoring and Alerting

| Name | Type | Scope | Description | Example |
|------|------|-------|-------------|---------|
| `ALARM_SNS_TOPIC_ARN` | Variable | Repository | SNS topic ARN for CloudWatch alarms and deployment notifications | `arn:aws:sns:us-east-1:123456789012:portfolio-optimizer-alerts` |

This SNS topic receives:
- CloudWatch alarm notifications (high error rate, CPU, memory)
- Deployment success/failure notifications from the CD workflow

Subscribe email addresses, Slack webhooks, or PagerDuty endpoints to this topic.

## Workflow Usage Reference

The table below shows which workflow uses each secret/variable:

| Name | `ci.yml` | `cd.yml` | `terraform.yml` |
|------|----------|----------|-----------------|
| `AWS_ACCOUNT_ID` | — | — | ✓ |
| `AWS_REGION` | — | ✓ | ✓ |
| `AWS_DEPLOY_ROLE_ARN` | — | ✓ | — |
| `AWS_ROLE_ARN` | — | — | ✓ |
| `PRODUCTION_ALB_URL` | — | ✓ | — |
| `STAGING_ALB_URL` | — | ✓ | — |
| `ECS_CLUSTER_NAME` | — | ✓ | — |
| `ECS_BACKEND_SERVICE` | — | ✓ | — |
| `ECS_WORKER_SERVICE` | — | ✓ | — |
| `ECS_FRONTEND_SERVICE` | — | ✓ | — |
| `ECS_MIGRATION_TASK_DEF` | — | ✓ | — |
| `ECS_SUBNET_IDS` | — | ✓ | — |
| `ECS_SECURITY_GROUP_ID` | — | ✓ | — |
| `ECR_REGISTRY` | — | ✓ | — |
| `TF_STATE_BUCKET` | — | — | ✓ |
| `TF_STATE_LOCK_TABLE` | — | — | ✓ |
| `OPENAI_API_KEY` | — | — | ✓ |
| `DB_PASSWORD` | — | — | ✓ |
| `REDIS_AUTH_TOKEN` | — | — | ✓ |
| `ACM_CERTIFICATE_ARN` | — | — | ✓ |
| `DOMAIN_NAME` | — | — | ✓ |
| `ALARM_SNS_TOPIC_ARN` | — | ✓ | ✓ |

## Security Best Practices

### Principle of Least Privilege

Create separate IAM roles for different workflow responsibilities:

```
AWS_DEPLOY_ROLE_ARN  →  ECS update-service, ECR push, ECS run-task
AWS_ROLE_ARN         →  Full Terraform provisioning (EC2, RDS, ECS, IAM, etc.)
```

Restrict the OIDC trust policy to specific branches:

```json
{
  "Condition": {
    "StringLike": {
      "token.actions.githubusercontent.com:sub": [
        "repo:your-org/portfolio-optimizer:ref:refs/heads/main",
        "repo:your-org/portfolio-optimizer:ref:refs/heads/develop"
      ]
    }
  }
}
```

### Secret Rotation

Rotate secrets regularly:

| Secret | Rotation Frequency | Method |
|--------|-------------------|--------|
| `DB_PASSWORD` | Every 90 days | AWS Secrets Manager rotation + update GitHub secret |
| `REDIS_AUTH_TOKEN` | Every 90 days | ElastiCache token rotation + update GitHub secret |
| `OPENAI_API_KEY` | When compromised or quarterly | OpenAI dashboard + update GitHub secret |

### Never Commit Secrets

Add these patterns to `.gitignore`:

```gitignore
# Terraform
*.tfvars
!*.tfvars.example
backend.hcl
!backend.hcl.example
.terraform/
terraform.tfstate
terraform.tfstate.backup

# Environment files
.env
.env.*
!.env.example
```

### Audit Secret Access

Enable AWS CloudTrail to log all `secretsmanager:GetSecretValue` calls. Set up a CloudWatch alarm for unexpected access patterns.

### Environment Protection Rules

Configure GitHub environment protection rules for `production`:

1. Go to **Settings** → **Environments** → **production**
2. Enable **Required reviewers** — require at least one team member to approve production deployments
3. Enable **Wait timer** — add a 5-minute delay before production deployments proceed
4. Restrict deployments to the `main` branch only

```yaml
# In your workflow, reference the environment:
environment:
  name: production
  url: https://${{ vars.PRODUCTION_ALB_URL }}
```

This causes the workflow to pause and request approval before running the `apply-production` job.

## Initial Setup Checklist

Use this checklist when setting up the CI/CD pipelines for the first time:

```
Bootstrap Phase:
  [ ] Run infra/terraform/bootstrap to create S3 bucket, DynamoDB table, OIDC role
  [ ] Note the outputs: bucket name, table name, role ARN

GitHub Configuration:
  [ ] Set AWS_ACCOUNT_ID (variable)
  [ ] Set AWS_REGION (variable)
  [ ] Set AWS_DEPLOY_ROLE_ARN (variable)
  [ ] Set AWS_ROLE_ARN (secret)
  [ ] Set ECR_REGISTRY (variable)
  [ ] Set TF_STATE_BUCKET (variable)
  [ ] Set TF_STATE_LOCK_TABLE (variable)
  [ ] Set OPENAI_API_KEY (secret)
  [ ] Set DB_PASSWORD (secret) — generate with: openssl rand -base64 32
  [ ] Set REDIS_AUTH_TOKEN (secret) — generate with: openssl rand -hex 32
  [ ] Set ACM_CERTIFICATE_ARN (variable) — create cert in ACM first
  [ ] Set DOMAIN_NAME (variable)
  [ ] Set ALARM_SNS_TOPIC_ARN (variable) — create SNS topic first

After First Terraform Apply:
  [ ] Set ECS_CLUSTER_NAME (variable) — from terraform output
  [ ] Set ECS_BACKEND_SERVICE (variable) — from terraform output
  [ ] Set ECS_WORKER_SERVICE (variable) — from terraform output
  [ ] Set ECS_FRONTEND_SERVICE (variable) — from terraform output
  [ ] Set ECS_MIGRATION_TASK_DEF (variable) — same as ECS_BACKEND_SERVICE
  [ ] Set ECS_SUBNET_IDS (variable) — from terraform output (private subnets)
  [ ] Set ECS_SECURITY_GROUP_ID (variable) — from terraform output (backend SG)
  [ ] Set PRODUCTION_ALB_URL (variable) — from terraform output
  [ ] Set STAGING_ALB_URL (variable) — from terraform output

Environment Protection:
  [ ] Create 'staging' environment in GitHub
  [ ] Create 'production' environment in GitHub
  [ ] Add required reviewers to production environment
  [ ] Restrict production to main branch only
```

## Related Pages

- [CI Workflow](ci-workflow.md) — continuous integration pipeline
- [CD Workflow](cd-workflow.md) — continuous deployment pipeline
- [Terraform Workflow](terraform-workflow.md) — infrastructure provisioning pipeline
