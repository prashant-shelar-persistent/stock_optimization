################################################################################
# VPC Module — Core VPC Infrastructure
#
# Provisions the foundational VPC resources required by the Portfolio Optimizer
# application on AWS ECS Fargate:
#
#   - VPC with configurable CIDR, DNS hostnames, and DNS resolution
#   - Custom DHCP options set (domain name + DNS servers)
#   - VPC Endpoints (Gateway: S3; Interface: ECR API, ECR DKR, Secrets Manager,
#     CloudWatch Logs, CloudWatch Monitoring, SSM, STS, ECS, ECS Agent, ECS Telemetry)
#     — eliminates NAT Gateway data-transfer costs for AWS API calls from private subnets
#   - VPC Flow Logs → CloudWatch Logs with a dedicated IAM role
#   - Optional secondary IPv4 CIDR blocks
#
# Design notes:
#   - The networking module (subnets, NAT, route tables) consumes this module's
#     outputs (vpc_id, vpc_cidr_block) to avoid circular dependencies.
#   - VPC Endpoints are placed in private subnets and associated with the
#     endpoint security group passed in via var.endpoint_security_group_id.
#   - Flow logs capture ALL traffic (ACCEPT + REJECT) for security auditing.
################################################################################

################################################################################
# VPC
################################################################################

resource "aws_vpc" "this" {
  cidr_block = var.vpc_cidr

  # DNS settings — required for ECS service discovery and RDS hostname resolution
  enable_dns_hostnames = var.enable_dns_hostnames
  enable_dns_support   = var.enable_dns_support

  # Instance tenancy — default is shared hardware (cost-effective)
  instance_tenancy = var.instance_tenancy

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpc"
  })
}

################################################################################
# Secondary CIDR Blocks (optional)
# Useful when the primary CIDR is exhausted or for VPC peering scenarios.
################################################################################

resource "aws_vpc_ipv4_cidr_block_association" "secondary" {
  count = length(var.secondary_cidr_blocks)

  vpc_id     = aws_vpc.this.id
  cidr_block = var.secondary_cidr_blocks[count.index]
}

################################################################################
# DHCP Options Set
#
# Configures DNS domain and servers for instances launched in the VPC.
# Using AmazonProvidedDNS ensures Route 53 Resolver is used for both
# internal (VPC-local) and external DNS resolution.
################################################################################

resource "aws_vpc_dhcp_options" "this" {
  domain_name         = var.dhcp_options_domain_name != "" ? var.dhcp_options_domain_name : "${var.aws_region}.compute.internal"
  domain_name_servers = var.dhcp_options_domain_name_servers

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-dhcp-options"
  })
}

resource "aws_vpc_dhcp_options_association" "this" {
  vpc_id          = aws_vpc.this.id
  dhcp_options_id = aws_vpc_dhcp_options.this.id
}

################################################################################
# VPC Flow Logs
#
# Captures all IP traffic (ACCEPT + REJECT) for security auditing and
# network troubleshooting. Logs are sent to CloudWatch Logs.
################################################################################

resource "aws_cloudwatch_log_group" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  name              = "/aws/vpc/${var.name_prefix}/flow-logs"
  retention_in_days = var.flow_logs_retention_days

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpc-flow-logs"
  })
}

resource "aws_iam_role" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  name = "${var.name_prefix}-vpc-flow-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "VPCFlowLogsAssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "vpc-flow-logs.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpc-flow-logs-role"
  })
}

resource "aws_iam_role_policy" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  name = "${var.name_prefix}-vpc-flow-logs-policy"
  role = aws_iam_role.flow_logs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudWatchLogs"
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_flow_log" "this" {
  count = var.enable_flow_logs ? 1 : 0

  vpc_id          = aws_vpc.this.id
  traffic_type    = var.flow_logs_traffic_type
  iam_role_arn    = aws_iam_role.flow_logs[0].arn
  log_destination = aws_cloudwatch_log_group.flow_logs[0].arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpc-flow-log"
  })

  depends_on = [aws_iam_role_policy.flow_logs]
}

################################################################################
# VPC Endpoints — Gateway Type
#
# Gateway endpoints are free and route traffic to S3 and DynamoDB without
# traversing the NAT Gateway, reducing data-transfer costs significantly.
################################################################################

# S3 Gateway Endpoint — used by ECS to pull container images from ECR
# (ECR stores image layers in S3) and for general S3 access.
resource "aws_vpc_endpoint" "s3" {
  count = var.enable_s3_endpoint ? 1 : 0

  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpce-s3"
  })
}

# DynamoDB Gateway Endpoint — optional, useful if DynamoDB is used for
# session storage or Terraform state locking.
resource "aws_vpc_endpoint" "dynamodb" {
  count = var.enable_dynamodb_endpoint ? 1 : 0

  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpce-dynamodb"
  })
}

################################################################################
# VPC Endpoints — Interface Type
#
# Interface endpoints create ENIs in private subnets, allowing ECS Fargate
# tasks to communicate with AWS services without leaving the VPC.
# This is critical for tasks in private subnets without NAT Gateway access
# to AWS APIs (ECR, Secrets Manager, CloudWatch, SSM, STS, ECS control plane).
#
# Cost note: Each interface endpoint incurs an hourly charge (~$0.01/hr/AZ).
# Enable selectively based on traffic volume vs. NAT Gateway data costs.
################################################################################

locals {
  # Interface endpoints to create when var.enable_interface_endpoints = true
  # Maps endpoint short name → AWS service name suffix
  interface_endpoints = var.enable_interface_endpoints ? {
    # ECR — required for ECS Fargate to pull container images
    "ecr-api" = "ecr.api"
    "ecr-dkr" = "ecr.dkr"

    # Secrets Manager — required for ECS tasks to fetch secrets at startup
    "secretsmanager" = "secretsmanager"

    # CloudWatch Logs — required for ECS task log delivery
    "logs" = "logs"

    # CloudWatch Monitoring — for custom metrics from the application
    "monitoring" = "monitoring"

    # SSM — for Systems Manager Parameter Store and Session Manager
    "ssm" = "ssm"
    "ssmmessages" = "ssmmessages"
    "ec2messages" = "ec2messages"

    # STS — required for IAM role assumption by ECS tasks
    "sts" = "sts"

    # ECS control plane — required for ECS agent communication
    "ecs" = "ecs"
    "ecs-agent" = "ecs-agent"
    "ecs-telemetry" = "ecs-telemetry"
  } : {}
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.aws_region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = var.endpoint_security_group_ids
  private_dns_enabled = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpce-${each.key}"
  })
}
