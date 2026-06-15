################################################################################
# Portfolio Optimizer — Root Module Outputs
################################################################################

# ── Networking ────────────────────────────────────────────────────────────────

output "vpc_id" {
  description = "ID of the VPC."
  value       = module.networking.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets."
  value       = module.networking.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of the private subnets."
  value       = module.networking.private_subnet_ids
}

# ── ECR ───────────────────────────────────────────────────────────────────────

output "ecr_backend_repository_url" {
  description = "ECR repository URL for the backend image."
  value       = module.ecr.repository_urls["backend"]
}

output "ecr_worker_repository_url" {
  description = "ECR repository URL for the worker image."
  value       = module.ecr.repository_urls["worker"]
}

output "ecr_frontend_repository_url" {
  description = "ECR repository URL for the frontend image."
  value       = module.ecr.repository_urls["frontend"]
}

# ── ALB ───────────────────────────────────────────────────────────────────────

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer."
  value       = module.alb.alb_dns_name
}

output "alb_zone_id" {
  description = "Hosted zone ID of the ALB (for Route 53 alias records)."
  value       = module.alb.alb_zone_id
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer."
  value       = module.alb.alb_arn
}

# ── RDS ───────────────────────────────────────────────────────────────────────

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (hostname only)."
  value       = module.rds.db_endpoint
  sensitive   = true
}

output "rds_port" {
  description = "RDS PostgreSQL port."
  value       = module.rds.db_port
}

# ── ElastiCache ───────────────────────────────────────────────────────────────

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint."
  value       = module.elasticache.redis_endpoint
  sensitive   = true
}

output "redis_port" {
  description = "ElastiCache Redis port."
  value       = module.elasticache.redis_port
}

# ── ECS ───────────────────────────────────────────────────────────────────────

output "ecs_cluster_name" {
  description = "Name of the ECS cluster."
  value       = module.ecs.cluster_name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster."
  value       = module.ecs.cluster_arn
}

output "backend_service_name" {
  description = "Name of the ECS backend service."
  value       = module.ecs.backend_service_name
}

output "worker_service_name" {
  description = "Name of the ECS worker service."
  value       = module.ecs.worker_service_name
}

output "frontend_service_name" {
  description = "Name of the ECS frontend service."
  value       = module.ecs.frontend_service_name
}

# ── IAM ───────────────────────────────────────────────────────────────────────

output "task_execution_role_arn" {
  description = "ARN of the ECS task execution IAM role."
  value       = module.iam.task_execution_role_arn
}

output "task_role_arn" {
  description = "ARN of the ECS task IAM role."
  value       = module.iam.task_role_arn
}

# ── Secrets ───────────────────────────────────────────────────────────────────

output "openai_api_key_secret_arn" {
  description = "ARN of the OpenAI API key secret in Secrets Manager."
  value       = module.secrets.openai_api_key_secret_arn
  sensitive   = true
}

output "db_password_secret_arn" {
  description = "ARN of the database password secret in Secrets Manager."
  value       = module.secrets.db_password_secret_arn
  sensitive   = true
}

# ── CloudWatch ────────────────────────────────────────────────────────────────

output "cloudwatch_log_group_backend" {
  description = "CloudWatch log group name for the backend service."
  value       = module.cloudwatch.log_group_backend
}

output "cloudwatch_log_group_worker" {
  description = "CloudWatch log group name for the worker service."
  value       = module.cloudwatch.log_group_worker
}

output "cloudwatch_log_group_frontend" {
  description = "CloudWatch log group name for the frontend service."
  value       = module.cloudwatch.log_group_frontend
}

# ── Security Groups ───────────────────────────────────────────────────────────

output "alb_security_group_id" {
  description = "ID of the ALB security group."
  value       = module.security_groups.alb_sg_id
}

output "backend_security_group_id" {
  description = "ID of the backend ECS security group."
  value       = module.security_groups.backend_sg_id
}

output "worker_security_group_id" {
  description = "ID of the worker ECS security group."
  value       = module.security_groups.worker_sg_id
}

# ── Convenience ───────────────────────────────────────────────────────────────

output "application_url" {
  description = "Primary URL to access the application."
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.alb.alb_dns_name}"
}

output "aws_account_id" {
  description = "AWS account ID where resources are deployed."
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region where resources are deployed."
  value       = data.aws_region.current.name
}
