################################################################################
# CloudWatch Module — Outputs
################################################################################

output "log_group_backend" {
  description = "Name of the backend CloudWatch log group."
  value       = aws_cloudwatch_log_group.backend.name
}

output "log_group_worker" {
  description = "Name of the worker CloudWatch log group."
  value       = aws_cloudwatch_log_group.worker.name
}

output "log_group_frontend" {
  description = "Name of the frontend CloudWatch log group."
  value       = aws_cloudwatch_log_group.frontend.name
}

output "log_group_arns" {
  description = "List of all CloudWatch log group ARNs."
  value = [
    aws_cloudwatch_log_group.backend.arn,
    aws_cloudwatch_log_group.worker.arn,
    aws_cloudwatch_log_group.frontend.arn,
  ]
}

output "alarm_backend_cpu_arn" {
  description = "ARN of the backend CPU alarm."
  value       = aws_cloudwatch_metric_alarm.backend_cpu.arn
}

output "alarm_backend_memory_arn" {
  description = "ARN of the backend memory alarm."
  value       = aws_cloudwatch_metric_alarm.backend_memory.arn
}

output "alarm_worker_cpu_arn" {
  description = "ARN of the worker CPU alarm."
  value       = aws_cloudwatch_metric_alarm.worker_cpu.arn
}

output "alarm_worker_memory_arn" {
  description = "ARN of the worker memory alarm."
  value       = aws_cloudwatch_metric_alarm.worker_memory.arn
}
