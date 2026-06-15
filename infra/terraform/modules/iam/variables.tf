################################################################################
# IAM Module — Variables
################################################################################

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID."
  type        = string
}

variable "aws_region" {
  description = "AWS region."
  type        = string
}

variable "secrets_arns" {
  description = "List of Secrets Manager secret ARNs that ECS tasks need to read."
  type        = list(string)
  sensitive   = true
}

variable "ecr_repository_arns" {
  description = "List of ECR repository ARNs that ECS tasks need to pull from."
  type        = list(string)
}

variable "cloudwatch_log_group_arns" {
  description = "List of CloudWatch log group ARNs that ECS tasks need to write to."
  type        = list(string)
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
