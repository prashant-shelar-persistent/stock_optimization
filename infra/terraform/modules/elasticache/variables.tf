################################################################################
# ElastiCache Module — Variables
################################################################################

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC."
  type        = string
}

variable "private_subnet_ids" {
  description = "IDs of private subnets for the ElastiCache subnet group."
  type        = list(string)
}

variable "redis_security_group_id" {
  description = "ID of the pre-created Redis security group."
  type        = string
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes (1 = no replication, 2+ = primary + replicas)."
  type        = number
  default     = 1
}

variable "redis_auth_token_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the Redis AUTH token."
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
