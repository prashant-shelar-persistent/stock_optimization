################################################################################
# VPC Module — Outputs
################################################################################

# ── VPC Core ──────────────────────────────────────────────────────────────────

output "vpc_id" {
  description = "ID of the VPC. Consumed by the networking, security_groups, rds, elasticache, alb, and ecs modules."
  value       = aws_vpc.this.id
}

output "vpc_arn" {
  description = "ARN of the VPC."
  value       = aws_vpc.this.arn
}

output "vpc_cidr_block" {
  description = "Primary IPv4 CIDR block of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "secondary_cidr_blocks" {
  description = "List of secondary IPv4 CIDR blocks associated with the VPC."
  value       = aws_vpc_ipv4_cidr_block_association.secondary[*].cidr_block
}

output "default_security_group_id" {
  description = "ID of the VPC's default security group. Note: the default SG should not be used — all traffic should be managed via explicit security groups."
  value       = aws_vpc.this.default_security_group_id
}

output "default_route_table_id" {
  description = "ID of the VPC's default route table."
  value       = aws_vpc.this.default_route_table_id
}

output "default_network_acl_id" {
  description = "ID of the VPC's default network ACL."
  value       = aws_vpc.this.default_network_acl_id
}

output "dhcp_options_id" {
  description = "ID of the custom DHCP options set associated with the VPC."
  value       = aws_vpc_dhcp_options.this.id
}

# ── VPC Flow Logs ─────────────────────────────────────────────────────────────

output "flow_log_id" {
  description = "ID of the VPC Flow Log resource. Empty string when flow logs are disabled."
  value       = var.enable_flow_logs ? aws_flow_log.this[0].id : ""
}

output "flow_log_cloudwatch_log_group_name" {
  description = "Name of the CloudWatch Log Group receiving VPC Flow Log entries. Empty string when flow logs are disabled."
  value       = var.enable_flow_logs ? aws_cloudwatch_log_group.flow_logs[0].name : ""
}

output "flow_log_cloudwatch_log_group_arn" {
  description = "ARN of the CloudWatch Log Group receiving VPC Flow Log entries. Empty string when flow logs are disabled."
  value       = var.enable_flow_logs ? aws_cloudwatch_log_group.flow_logs[0].arn : ""
}

output "flow_log_iam_role_arn" {
  description = "ARN of the IAM role used by VPC Flow Logs to write to CloudWatch. Empty string when flow logs are disabled."
  value       = var.enable_flow_logs ? aws_iam_role.flow_logs[0].arn : ""
}

# ── VPC Endpoints — Gateway ───────────────────────────────────────────────────

output "s3_endpoint_id" {
  description = "ID of the S3 Gateway VPC Endpoint. Empty string when the endpoint is disabled."
  value       = var.enable_s3_endpoint ? aws_vpc_endpoint.s3[0].id : ""
}

output "dynamodb_endpoint_id" {
  description = "ID of the DynamoDB Gateway VPC Endpoint. Empty string when the endpoint is disabled."
  value       = var.enable_dynamodb_endpoint ? aws_vpc_endpoint.dynamodb[0].id : ""
}

# ── VPC Endpoints — Interface ─────────────────────────────────────────────────

output "interface_endpoint_ids" {
  description = "Map of interface VPC endpoint short names to their endpoint IDs. Empty map when interface endpoints are disabled."
  value = {
    for k, ep in aws_vpc_endpoint.interface : k => ep.id
  }
}

output "interface_endpoint_dns_entries" {
  description = "Map of interface VPC endpoint short names to their DNS entries. Useful for debugging connectivity from ECS tasks."
  value = {
    for k, ep in aws_vpc_endpoint.interface : k => ep.dns_entry
  }
}
