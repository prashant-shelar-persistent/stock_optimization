################################################################################
# Secrets Module — Outputs
################################################################################

output "openai_api_key_secret_arn" {
  description = "ARN of the OpenAI API key secret."
  value       = aws_secretsmanager_secret.openai_api_key.arn
  sensitive   = true
}

output "db_password_secret_arn" {
  description = "ARN of the database password secret."
  value       = aws_secretsmanager_secret.db_password.arn
  sensitive   = true
}

output "redis_auth_token_secret_arn" {
  description = "ARN of the Redis AUTH token secret."
  value       = aws_secretsmanager_secret.redis_auth_token.arn
  sensitive   = true
}

output "all_secret_arns" {
  description = "List of all secret ARNs (for IAM policy attachment)."
  value = [
    aws_secretsmanager_secret.openai_api_key.arn,
    aws_secretsmanager_secret.db_password.arn,
    aws_secretsmanager_secret.redis_auth_token.arn,
  ]
  sensitive = true
}
