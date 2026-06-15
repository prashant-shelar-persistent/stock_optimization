################################################################################
# ECR Module — Variables
################################################################################

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
}

variable "repositories" {
  description = "Map of repository key to repository name suffix."
  type        = map(string)
  default = {
    backend  = "backend"
    worker   = "worker"
    frontend = "frontend"
  }
}

variable "image_retention_count" {
  description = "Number of tagged images to retain per repository."
  type        = number
  default     = 10
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
