################################################################################
# ECS Module — Outputs
################################################################################

output "cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  description = "ARN of the ECS cluster."
  value       = aws_ecs_cluster.main.arn
}

output "backend_service_name" {
  description = "Name of the backend ECS service."
  value       = aws_ecs_service.backend.name
}

output "backend_service_arn" {
  description = "ARN of the backend ECS service."
  value       = aws_ecs_service.backend.id
}

output "worker_service_name" {
  description = "Name of the worker ECS service."
  value       = aws_ecs_service.worker.name
}

output "worker_service_arn" {
  description = "ARN of the worker ECS service."
  value       = aws_ecs_service.worker.id
}

output "frontend_service_name" {
  description = "Name of the frontend ECS service."
  value       = aws_ecs_service.frontend.name
}

output "frontend_service_arn" {
  description = "ARN of the frontend ECS service."
  value       = aws_ecs_service.frontend.id
}

output "backend_task_definition_arn" {
  description = "ARN of the latest backend task definition."
  value       = aws_ecs_task_definition.backend.arn
}

output "worker_task_definition_arn" {
  description = "ARN of the latest worker task definition."
  value       = aws_ecs_task_definition.worker.arn
}

output "frontend_task_definition_arn" {
  description = "ARN of the latest frontend task definition."
  value       = aws_ecs_task_definition.frontend.arn
}
