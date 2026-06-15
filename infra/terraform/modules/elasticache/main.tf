################################################################################
# ElastiCache Module — Redis 7 (Replication Group)
#
# Note: The Redis security group is created in the security_groups module
#       and passed in via var.redis_security_group_id to avoid circular deps.
################################################################################

################################################################################
# Subnet Group
################################################################################

resource "aws_elasticache_subnet_group" "main" {
  name        = "${var.name_prefix}-redis-subnet-group"
  description = "Subnet group for ${var.name_prefix} ElastiCache Redis"
  subnet_ids  = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-subnet-group"
  })
}

################################################################################
# Parameter Group
################################################################################

resource "aws_elasticache_parameter_group" "main" {
  name        = "${var.name_prefix}-redis7-params"
  family      = "redis7"
  description = "Custom parameter group for ${var.name_prefix} Redis 7"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }

  parameter {
    name  = "activerehashing"
    value = "yes"
  }

  parameter {
    name  = "lazyfree-lazy-eviction"
    value = "yes"
  }

  tags = var.tags
}

################################################################################
# Replication Group (Redis 7)
################################################################################

# Retrieve the auth token from Secrets Manager
data "aws_secretsmanager_secret_version" "redis_auth_token" {
  secret_id = var.redis_auth_token_secret_arn
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "Redis 7 replication group for ${var.name_prefix}"

  # Engine
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.redis_node_type
  parameter_group_name = aws_elasticache_parameter_group.main.name
  port                 = 6379

  # Cluster configuration (single shard, no cluster mode)
  num_cache_clusters         = var.redis_num_cache_nodes
  automatic_failover_enabled = var.redis_num_cache_nodes > 1 ? true : false
  multi_az_enabled           = var.redis_num_cache_nodes > 1 ? true : false

  # Network
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [var.redis_security_group_id]

  # Security
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = data.aws_secretsmanager_secret_version.redis_auth_token.secret_string

  # Maintenance
  maintenance_window       = "sun:05:00-sun:06:00"
  snapshot_window          = "04:00-05:00"
  snapshot_retention_limit = 3

  # Auto minor version upgrades
  auto_minor_version_upgrade = true

  # Apply changes immediately in non-production
  apply_immediately = false

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis"
  })
}
