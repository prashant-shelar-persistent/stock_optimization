################################################################################
# ALB Module — Variables
################################################################################

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC."
  type        = string
}

variable "public_subnet_ids" {
  description = "IDs of public subnets for the ALB."
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "ID of the pre-created ALB security group."
  type        = string
}

variable "certificate_arn" {
  description = "ARN of the ACM certificate for HTTPS. Leave empty to skip HTTPS listener."
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Primary domain name for the application."
  type        = string
  default     = ""
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection on the ALB."
  type        = bool
  default     = false
}

variable "access_logs_bucket" {
  description = "S3 bucket name for ALB access logs. Leave empty to disable."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
