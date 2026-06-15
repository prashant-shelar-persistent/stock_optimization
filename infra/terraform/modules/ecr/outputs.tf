################################################################################
# ECR Module — Outputs
################################################################################

output "repository_urls" {
  description = "Map of repository key to repository URL."
  value       = { for k, v in aws_ecr_repository.repos : k => v.repository_url }
}

output "repository_arns" {
  description = "List of all ECR repository ARNs."
  value       = [for v in aws_ecr_repository.repos : v.arn]
}

output "repository_names" {
  description = "Map of repository key to repository name."
  value       = { for k, v in aws_ecr_repository.repos : k => v.name }
}
