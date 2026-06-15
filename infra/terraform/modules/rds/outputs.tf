################################################################################
# RDS Module — Outputs
################################################################################

output "db_endpoint" {
  description = "RDS instance endpoint (hostname only, without port)."
  value       = aws_db_instance.main.address
  sensitive   = true
}

output "db_port" {
  description = "RDS instance port."
  value       = aws_db_instance.main.port
}

output "db_identifier" {
  description = "RDS instance identifier."
  value       = aws_db_instance.main.identifier
}

output "db_arn" {
  description = "ARN of the RDS instance."
  value       = aws_db_instance.main.arn
}

output "db_subnet_group_name" {
  description = "Name of the DB subnet group."
  value       = aws_db_subnet_group.main.name
}
