################################################################################
# RDS Module — Variables
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
  description = "IDs of private subnets for the DB subnet group."
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "ID of the pre-created RDS security group."
  type        = string
}

variable "db_name" {
  description = "Name of the PostgreSQL database."
  type        = string
  default     = "portfolio_optimizer"
}

variable "db_username" {
  description = "PostgreSQL master username."
  type        = string
}

variable "db_password_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the DB password."
  type        = string
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Initial allocated storage in GiB."
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Enable Multi-AZ deployment."
  type        = bool
  default     = true
}

variable "db_deletion_protection" {
  description = "Enable deletion protection."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "Number of days to retain automated backups."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
