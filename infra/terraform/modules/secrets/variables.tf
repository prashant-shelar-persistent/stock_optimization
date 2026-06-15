################################################################################
# Secrets Module — Variables
################################################################################

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
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

variable "recovery_window_in_days" {
  description = "Number of days before a deleted secret is permanently removed."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
