################################################################################
# ECS Module — Variables
################################################################################

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC."
  type        = string
}

variable "private_subnet_ids" {
  description = "IDs of private subnets for ECS tasks."
  type        = list(string)
}

variable "alb_target_group_backend_arn" {
  description = "ARN of the ALB target group for the backend service."
  type        = string
}

variable "alb_target_group_frontend_arn" {
  description = "ARN of the ALB target group for the frontend service."
  type        = string
}

# ── Pre-created Security Groups ───────────────────────────────────────────────

variable "backend_security_group_id" {
  description = "ID of the pre-created backend ECS security group."
  type        = string
}

variable "worker_security_group_id" {
  description = "ID of the pre-created worker ECS security group."
  type        = string
}

variable "frontend_security_group_id" {
  description = "ID of the pre-created frontend ECS security group."
  type        = string
}

# ── Image URIs ────────────────────────────────────────────────────────────────

variable "backend_image_uri" {
  description = "Full ECR image URI for the backend service (including tag)."
  type        = string
}

variable "worker_image_uri" {
  description = "Full ECR image URI for the worker service (including tag)."
  type        = string
}

variable "frontend_image_uri" {
  description = "Full ECR image URI for the frontend service (including tag)."
  type        = string
}

# ── IAM ───────────────────────────────────────────────────────────────────────

variable "task_execution_role_arn" {
  description = "ARN of the ECS task execution role."
  type        = string
}

variable "task_role_arn" {
  description = "ARN of the ECS task role."
  type        = string
}

# ── Secrets ───────────────────────────────────────────────────────────────────

variable "openai_api_key_secret_arn" {
  description = "ARN of the OpenAI API key secret."
  type        = string
  sensitive   = true
}

variable "db_password_secret_arn" {
  description = "ARN of the database password secret."
  type        = string
  sensitive   = true
}

variable "redis_auth_token_secret_arn" {
  description = "ARN of the Redis AUTH token secret."
  type        = string
  sensitive   = true
}

# ── Database ──────────────────────────────────────────────────────────────────

variable "db_host" {
  description = "RDS PostgreSQL hostname."
  type        = string
  sensitive   = true
}

variable "db_port" {
  description = "RDS PostgreSQL port."
  type        = number
  default     = 5432
}

variable "db_name" {
  description = "PostgreSQL database name."
  type        = string
}

variable "db_username" {
  description = "PostgreSQL username."
  type        = string
}

# ── Redis ─────────────────────────────────────────────────────────────────────

variable "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint."
  type        = string
  sensitive   = true
}

variable "redis_port" {
  description = "ElastiCache Redis port."
  type        = number
  default     = 6379
}

# ── CloudWatch ────────────────────────────────────────────────────────────────

variable "cloudwatch_log_group_backend" {
  description = "CloudWatch log group name for the backend service."
  type        = string
}

variable "cloudwatch_log_group_worker" {
  description = "CloudWatch log group name for the worker service."
  type        = string
}

variable "cloudwatch_log_group_frontend" {
  description = "CloudWatch log group name for the frontend service."
  type        = string
}

# ── Task Sizing ───────────────────────────────────────────────────────────────

variable "backend_cpu" {
  description = "CPU units for the backend Fargate task."
  type        = number
  default     = 1024
}

variable "backend_memory" {
  description = "Memory (MiB) for the backend Fargate task."
  type        = number
  default     = 2048
}

variable "worker_cpu" {
  description = "CPU units for the worker Fargate task."
  type        = number
  default     = 2048
}

variable "worker_memory" {
  description = "Memory (MiB) for the worker Fargate task."
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

# ── Desired Counts ────────────────────────────────────────────────────────────

variable "backend_desired_count" {
  description = "Desired number of backend task replicas."
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Desired number of worker task replicas."
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
  description = "Minimum number of backend tasks."
  type        = number
  default     = 2
}

variable "backend_max_capacity" {
  description = "Maximum number of backend tasks."
  type        = number
  default     = 10
}

variable "worker_min_capacity" {
  description = "Minimum number of worker tasks."
  type        = number
  default     = 1
}

variable "worker_max_capacity" {
  description = "Maximum number of worker tasks."
  type        = number
  default     = 8
}

# ── App Config ────────────────────────────────────────────────────────────────

variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "log_level" {
  description = "Application log level."
  type        = string
  default     = "INFO"
}

variable "quantum_timeout_seconds" {
  description = "Timeout for quantum optimization jobs."
  type        = number
  default     = 60
}

variable "max_quantum_assets" {
  description = "Maximum assets for quantum optimization."
  type        = number
  default     = 8
}

variable "cache_ttl_seconds" {
  description = "Default Redis cache TTL."
  type        = number
  default     = 3600
}

variable "risk_free_rate" {
  description = "Risk-free rate for Sharpe ratio calculations."
  type        = number
  default     = 0.02
}

variable "domain_name" {
  description = "Primary domain name for the application."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
