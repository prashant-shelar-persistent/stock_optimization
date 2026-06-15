################################################################################
# Portfolio Optimizer — Root Module Variables
################################################################################

# ── Project Identity ──────────────────────────────────────────────────────────

variable "project_name" {
  description = "Short name used as a prefix for all AWS resource names."
  type        = string
  default     = "portfolio-optimizer"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,28}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 4-30 lowercase alphanumeric characters or hyphens, starting with a letter."
  }
}

variable "environment" {
  description = "Deployment environment (development | staging | production)."
  type        = string

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "environment must be one of: development, staging, production."
  }
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)."
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)."
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "enable_nat_gateway" {
  description = "Whether to create NAT Gateway(s) for private subnet internet access."
  type        = bool
  default     = true
}

variable "single_nat_gateway" {
  description = "Use a single NAT Gateway (cost saving for non-production). Set false for HA in production."
  type        = bool
  default     = false
}

# ── ECR ───────────────────────────────────────────────────────────────────────

variable "ecr_image_retention_count" {
  description = "Number of images to retain in each ECR repository."
  type        = number
  default     = 10
}

variable "backend_image_tag" {
  description = "Docker image tag for the backend (FastAPI) service."
  type        = string
  default     = "latest"
}

variable "worker_image_tag" {
  description = "Docker image tag for the Celery worker service."
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Docker image tag for the frontend (Nginx) service."
  type        = string
  default     = "latest"
}

# ── Secrets ───────────────────────────────────────────────────────────────────

variable "openai_api_key" {
  description = "OpenAI API key stored in AWS Secrets Manager."
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL master password stored in AWS Secrets Manager."
  type        = string
  sensitive   = true
}

variable "redis_auth_token" {
  description = "Redis AUTH token stored in AWS Secrets Manager."
  type        = string
  sensitive   = true
}

# ── RDS ───────────────────────────────────────────────────────────────────────

variable "db_name" {
  description = "Name of the PostgreSQL database."
  type        = string
  default     = "portfolio_optimizer"
}

variable "db_username" {
  description = "PostgreSQL master username."
  type        = string
  default     = "portfolio_admin"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS in GiB."
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Enable Multi-AZ for RDS (recommended for production)."
  type        = bool
  default     = true
}

variable "db_deletion_protection" {
  description = "Enable deletion protection on the RDS instance."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "Number of days to retain automated RDS backups."
  type        = number
  default     = 7
}

# ── ElastiCache ───────────────────────────────────────────────────────────────

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes in the ElastiCache cluster."
  type        = number
  default     = 1
}

# ── ALB / DNS ─────────────────────────────────────────────────────────────────

variable "acm_certificate_arn" {
  description = "ARN of the ACM certificate for HTTPS on the ALB. Leave empty to skip HTTPS listener."
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Primary domain name for the application (e.g., portfolio-optimizer.example.com)."
  type        = string
  default     = ""
}

# ── ECS Task Sizing ───────────────────────────────────────────────────────────

variable "backend_cpu" {
  description = "CPU units for the backend Fargate task (1024 = 1 vCPU)."
  type        = number
  default     = 1024
}

variable "backend_memory" {
  description = "Memory (MiB) for the backend Fargate task."
  type        = number
  default     = 2048
}

variable "worker_cpu" {
  description = "CPU units for the Celery worker Fargate task."
  type        = number
  default     = 2048
}

variable "worker_memory" {
  description = "Memory (MiB) for the Celery worker Fargate task."
  type        = number
  default     = 4096
}

variable "frontend_cpu" {
  description = "CPU units for the frontend Fargate task."
  type        = number
  default     = 256
}

variable "frontend_memory" {
  description = "Memory (MiB) for the frontend Fargate task."
  type        = number
  default     = 512
}

# ── ECS Desired Counts ────────────────────────────────────────────────────────

variable "backend_desired_count" {
  description = "Desired number of backend task replicas."
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Desired number of Celery worker task replicas."
  type        = number
  default     = 2
}

variable "frontend_desired_count" {
  description = "Desired number of frontend task replicas."
  type        = number
  default     = 2
}

# ── Auto-scaling ──────────────────────────────────────────────────────────────

variable "backend_min_capacity" {
  description = "Minimum number of backend tasks for auto-scaling."
  type        = number
  default     = 2
}

variable "backend_max_capacity" {
  description = "Maximum number of backend tasks for auto-scaling."
  type        = number
  default     = 10
}

variable "worker_min_capacity" {
  description = "Minimum number of worker tasks for auto-scaling."
  type        = number
  default     = 1
}

variable "worker_max_capacity" {
  description = "Maximum number of worker tasks for auto-scaling."
  type        = number
  default     = 8
}

# ── CloudWatch ────────────────────────────────────────────────────────────────

variable "cloudwatch_log_retention_days" {
  description = "Number of days to retain CloudWatch log groups."
  type        = number
  default     = 30
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarm notifications. Leave empty to skip."
  type        = string
  default     = ""
}

# ── Application Config ────────────────────────────────────────────────────────

variable "log_level" {
  description = "Application log level (DEBUG | INFO | WARNING | ERROR)."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be one of: DEBUG, INFO, WARNING, ERROR."
  }
}

variable "quantum_timeout_seconds" {
  description = "Timeout in seconds for quantum optimization jobs."
  type        = number
  default     = 60
}

variable "max_quantum_assets" {
  description = "Maximum number of assets allowed in quantum optimization."
  type        = number
  default     = 8
}

variable "cache_ttl_seconds" {
  description = "Default TTL in seconds for Redis cache entries."
  type        = number
  default     = 3600
}

variable "risk_free_rate" {
  description = "Risk-free rate used in Sharpe ratio calculations."
  type        = number
  default     = 0.02
}
