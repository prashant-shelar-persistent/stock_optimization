################################################################################
# Staging Environment — Variables
################################################################################

variable "aws_region" {
  description = "AWS region for staging deployment."
  type        = string
  default     = "us-east-1"
}

variable "backend_image_tag" {
  description = "Docker image tag for the backend service."
  type        = string
  default     = "latest"
}

variable "worker_image_tag" {
  description = "Docker image tag for the worker service."
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Docker image tag for the frontend service."
  type        = string
  default     = "latest"
}

variable "openai_api_key" {
  description = "OpenAI API key."
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL master password."
  type        = string
  sensitive   = true
}

variable "redis_auth_token" {
  description = "Redis AUTH token."
  type        = string
  sensitive   = true
}

variable "acm_certificate_arn" {
  description = "ARN of the ACM certificate for HTTPS."
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Domain name for the staging environment."
  type        = string
  default     = ""
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarm notifications."
  type        = string
  default     = ""
}
