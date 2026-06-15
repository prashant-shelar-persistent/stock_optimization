################################################################################
# ElastiCache Module — Outputs
################################################################################

output "redis_endpoint" {
  description = "Primary endpoint address for the Redis replication group."
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
  sensitive   = true
}

output "redis_port" {
  description = "Redis port."
  value       = aws_elasticache_replication_group.main.port
}

output "redis_replication_group_id" {
  description = "ID of the ElastiCache replication group."
  value       = aws_elasticache_replication_group.main.id
}

output "redis_security_group_id" {
  description = "ID of the Redis security group."
  value       = aws_security_group.redis.id
}

output "redis_connection_url" {
  description = "Redis connection URL (without auth token)."
  value       = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:${aws_elasticache_replication_group.main.port}"
  sensitive   = true
}
