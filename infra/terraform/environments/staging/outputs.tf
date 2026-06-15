################################################################################
# Staging Environment — Outputs
################################################################################

output "application_url" {
  description = "Primary URL to access the staging application."
  value       = module.portfolio_optimizer.application_url
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer."
  value       = module.portfolio_optimizer.alb_dns_name
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
