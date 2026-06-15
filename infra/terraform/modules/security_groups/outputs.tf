################################################################################
# Security Groups Module — Outputs
################################################################################

output "alb_sg_id" {
  description = "ID of the ALB security group."
  value       = aws_security_group.alb.id
}

output "backend_sg_id" {
  description = "ID of the backend ECS security group."
  value       = aws_security_group.backend.id
}

output "worker_sg_id" {
  description = "ID of the worker ECS security group."
  value       = aws_security_group.worker.id
}

output "frontend_sg_id" {
  description = "ID of the frontend ECS security group."
  value       = aws_security_group.frontend.id
}

output "rds_sg_id" {
  description = "ID of the RDS security group."
  value       = aws_security_group.rds.id
}

output "redis_sg_id" {
  description = "ID of the Redis security group."
  value       = aws_security_group.redis.id
}
