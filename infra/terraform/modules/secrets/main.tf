################################################################################
# Secrets Module — AWS Secrets Manager
#
# Stores sensitive application configuration:
#   - OpenAI API key
#   - PostgreSQL master password
#   - Redis AUTH token
################################################################################

resource "aws_secretsmanager_secret" "openai_api_key" {
  name                    = "${var.name_prefix}/openai-api-key"
  description             = "OpenAI API key for LLM explanation node (GPT-4o)"
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-openai-api-key"
  })
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = var.openai_api_key
}

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${var.name_prefix}/db-password"
  description             = "PostgreSQL master password for portfolio_optimizer database"
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-db-password"
  })
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = var.db_password
}

resource "aws_secretsmanager_secret" "redis_auth_token" {
  name                    = "${var.name_prefix}/redis-auth-token"
  description             = "Redis AUTH token for ElastiCache"
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-auth-token"
  })
}

resource "aws_secretsmanager_secret_version" "redis_auth_token" {
  secret_id     = aws_secretsmanager_secret.redis_auth_token.id
  secret_string = var.redis_auth_token
}
