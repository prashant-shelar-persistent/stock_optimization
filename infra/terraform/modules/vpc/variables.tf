################################################################################
# VPC Module — Variables
################################################################################

# ── Identity ──────────────────────────────────────────────────────────────────

variable "name_prefix" {
  description = "Prefix applied to every resource name created by this module (e.g. 'portfolio-optimizer-production')."
  type        = string

  validation {
    condition     = length(var.name_prefix) > 0 && length(var.name_prefix) <= 50
    error_message = "name_prefix must be between 1 and 50 characters."
  }
}

variable "aws_region" {
  description = "AWS region in which the VPC is deployed. Used to construct VPC endpoint service names."
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Map of tags to apply to all resources created by this module."
  type        = map(string)
  default     = {}
}

# ── VPC Core ──────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "Primary IPv4 CIDR block for the VPC (e.g. '10.0.0.0/16'). Must be a valid RFC 1918 private range."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block (e.g. '10.0.0.0/16')."
  }
}

variable "secondary_cidr_blocks" {
  description = "Optional list of secondary IPv4 CIDR blocks to associate with the VPC. Useful when the primary CIDR is exhausted or for VPC peering."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for cidr in var.secondary_cidr_blocks : can(cidrhost(cidr, 0))])
    error_message = "All entries in secondary_cidr_blocks must be valid IPv4 CIDR blocks."
  }
}

variable "enable_dns_hostnames" {
  description = "Enable DNS hostnames in the VPC. Required for ECS service discovery and RDS hostname resolution."
  type        = bool
  default     = true
}

variable "enable_dns_support" {
  description = "Enable DNS resolution via the Amazon-provided DNS server (Route 53 Resolver). Must be true when enable_dns_hostnames is true."
  type        = bool
  default     = true
}

variable "instance_tenancy" {
  description = "Tenancy option for instances launched in the VPC. Use 'default' for shared hardware (cost-effective) or 'dedicated' for compliance requirements."
  type        = string
  default     = "default"

  validation {
    condition     = contains(["default", "dedicated"], var.instance_tenancy)
    error_message = "instance_tenancy must be either 'default' or 'dedicated'."
  }
}

# ── DHCP Options ──────────────────────────────────────────────────────────────

variable "dhcp_options_domain_name" {
  description = "Domain name for the DHCP options set. Defaults to '<region>.compute.internal' when left empty, which is the AWS standard for EC2 instances."
  type        = string
  default     = ""
}

variable "dhcp_options_domain_name_servers" {
  description = "List of DNS server addresses for the DHCP options set. 'AmazonProvidedDNS' uses the Route 53 Resolver at the VPC base + 2 address."
  type        = list(string)
  default     = ["AmazonProvidedDNS"]
}

# ── VPC Flow Logs ─────────────────────────────────────────────────────────────

variable "enable_flow_logs" {
  description = "Enable VPC Flow Logs to CloudWatch Logs. Recommended for all environments for security auditing and network troubleshooting."
  type        = bool
  default     = true
}

variable "flow_logs_traffic_type" {
  description = "Type of traffic to capture in VPC Flow Logs. 'ALL' captures both accepted and rejected traffic."
  type        = string
  default     = "ALL"

  validation {
    condition     = contains(["ACCEPT", "REJECT", "ALL"], var.flow_logs_traffic_type)
    error_message = "flow_logs_traffic_type must be one of: ACCEPT, REJECT, ALL."
  }
}

variable "flow_logs_retention_days" {
  description = "Number of days to retain VPC Flow Log entries in CloudWatch Logs."
  type        = number
  default     = 14

  validation {
    condition     = contains([0, 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.flow_logs_retention_days)
    error_message = "flow_logs_retention_days must be a valid CloudWatch Logs retention period (0 = never expire)."
  }
}

# ── VPC Endpoints — Gateway ───────────────────────────────────────────────────

variable "enable_s3_endpoint" {
  description = "Create a Gateway VPC Endpoint for S3. Eliminates NAT Gateway costs for S3 traffic (e.g. ECR image layer pulls). Requires private_route_table_ids."
  type        = bool
  default     = true
}

variable "enable_dynamodb_endpoint" {
  description = "Create a Gateway VPC Endpoint for DynamoDB. Useful if DynamoDB is used for Terraform state locking or application data."
  type        = bool
  default     = false
}

variable "private_route_table_ids" {
  description = "List of private route table IDs to associate with Gateway VPC Endpoints (S3, DynamoDB). Provided by the networking module after subnet creation."
  type        = list(string)
  default     = []
}

# ── VPC Endpoints — Interface ─────────────────────────────────────────────────

variable "enable_interface_endpoints" {
  description = <<-EOT
    Create Interface VPC Endpoints for AWS services used by ECS Fargate tasks
    (ECR API, ECR DKR, Secrets Manager, CloudWatch Logs, CloudWatch Monitoring,
    SSM, STS, ECS control plane). Eliminates NAT Gateway data-transfer costs
    for AWS API calls from private subnets.

    Note: Each interface endpoint incurs an hourly charge (~$0.01/hr/AZ).
    Recommended for production; optional for staging/development.
  EOT
  type        = bool
  default     = false
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs in which to place Interface VPC Endpoint ENIs. Required when enable_interface_endpoints = true."
  type        = list(string)
  default     = []
}

variable "endpoint_security_group_ids" {
  description = "List of security group IDs to associate with Interface VPC Endpoints. Should allow HTTPS (443) inbound from ECS task security groups."
  type        = list(string)
  default     = []
}
