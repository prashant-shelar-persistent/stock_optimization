################################################################################
# Bootstrap — Outputs
#
# Use these values to configure backend.hcl in each environment.
################################################################################

output "state_bucket_name" {
  description = "Name of the S3 bucket for Terraform state. Use in backend.hcl."
  value       = aws_s3_bucket.terraform_state.bucket
}

output "state_bucket_arn" {
  description = "ARN of the S3 bucket for Terraform state."
  value       = aws_s3_bucket.terraform_state.arn
}

output "state_lock_table_name" {
  description = "Name of the DynamoDB table for state locking. Use in backend.hcl."
  value       = aws_dynamodb_table.terraform_state_lock.name
}

output "github_actions_role_arn" {
  description = "ARN of the GitHub Actions IAM role. Set as AWS_ROLE_ARN GitHub secret."
  value       = length(aws_iam_role.github_actions) > 0 ? aws_iam_role.github_actions[0].arn : "not created"
}

output "backend_hcl_content" {
  description = "Content to put in backend.hcl for production environment."
  value       = <<-EOT
    bucket         = "${aws_s3_bucket.terraform_state.bucket}"
    key            = "portfolio-optimizer/production/terraform.tfstate"
    region         = "${var.aws_region}"
    dynamodb_table = "${aws_dynamodb_table.terraform_state_lock.name}"
    encrypt        = true
  EOT
}
