################################################################################
# CloudWatch Module — Variables
################################################################################

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch log groups."
  type        = number
  default     = 30
}

variable "alb_arn_suffix" {
  description = "ARN suffix of the ALB (used in CloudWatch metric dimensions)."
  type        = string
  default     = ""
}

variable "backend_service_name" {
  description = "Name of the ECS backend service."
  type        = string
}

variable "worker_service_name" {
  description = "Name of the ECS worker service."
  type        = string
}

variable "ecs_cluster_name" {
  description = "Name of the ECS cluster."
  type        = string
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarm notifications. Leave empty to skip."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
