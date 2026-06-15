################################################################################
# Bootstrap — Variables
################################################################################

variable "project_name" {
  description = "Project name used as prefix for state bucket and lock table."
  type        = string
  default     = "portfolio-optimizer"
}

variable "aws_region" {
  description = "AWS region for the state backend resources."
  type        = string
  default     = "us-east-1"
}

variable "create_github_oidc_provider" {
  description = "Whether to create the GitHub Actions OIDC provider. Set false if it already exists in the account."
  type        = bool
  default     = true
}

variable "create_github_oidc_role" {
  description = "Whether to create the GitHub Actions IAM role."
  type        = bool
  default     = true
}

variable "github_org" {
  description = "GitHub organization or username (used in OIDC trust policy)."
  type        = string
  default     = "your-github-org"
}

variable "github_repo" {
  description = "GitHub repository name (used in OIDC trust policy)."
  type        = string
  default     = "portfolio-optimizer"
}
