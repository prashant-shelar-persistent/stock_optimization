################################################################################
# Production Environment — Outputs
################################################################################

output "application_url" {
  description = "Primary URL to access the application."
  value       = module.portfolio_optimizer.application_url
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer."
  value       = module.portfolio_optimizer.alb_dns_name
}

output "alb_zone_id" {
  description = "Hosted zone ID of the ALB (for Route 53 alias records)."
  value       = module.portfolio_optimizer.alb_zone_id
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster."
  value       = module.portfolio_optimizer.ecs_cluster_name
}

output "ecr_backend_repository_url" {
  description = "ECR repository URL for the backend image."
  value       = module.portfolio_optimizer.ecr_backend_repository_url
}

output "ecr_worker_repository_url" {
  description = "ECR repository URL for the worker image."
  value       = module.portfolio_optimizer.ecr_worker_repository_url
}

output "ecr_frontend_repository_url" {
  description = "ECR repository URL for the frontend image."
  value       = module.portfolio_optimizer.ecr_frontend_repository_url
}

output "vpc_id" {
  description = "ID of the VPC."
  value       = module.portfolio_optimizer.vpc_id
}

output "aws_region" {
  description = "AWS region."
  value       = module.portfolio_optimizer.aws_region
}

output "aws_account_id" {
  description = "AWS account ID."
  value       = module.portfolio_optimizer.aws_account_id
}
