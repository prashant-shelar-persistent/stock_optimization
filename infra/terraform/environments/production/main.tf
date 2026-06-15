################################################################################
# Production Environment — Terraform Configuration
#
# This file wires the root module with production-specific settings.
# All sensitive values are provided via terraform.tfvars (not committed to VCS)
# or via AWS Secrets Manager / environment variables.
#
# Usage:
#   cd infra/terraform/environments/production
#   terraform init -backend-config=backend.hcl
#   terraform plan -var-file="terraform.tfvars"
#   terraform apply -var-file="terraform.tfvars"
################################################################################

terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  # Remote state in S3 with DynamoDB locking
  # Configure via backend.hcl (not committed to VCS):
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "portfolio-optimizer/production/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-state-lock"
  #   encrypt        = true
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "portfolio-optimizer"
      Environment = "production"
      ManagedBy   = "terraform"
    }
  }
}

################################################################################
# Root Module
################################################################################

module "portfolio_optimizer" {
  source = "../../"

  # Identity
  project_name = "portfolio-optimizer"
  environment  = "production"
  aws_region   = var.aws_region

  # Networking — production uses multi-NAT for HA
  vpc_cidr             = "10.0.0.0/16"
  public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
  private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
  enable_nat_gateway   = true
  single_nat_gateway   = false # HA: one NAT per AZ

  # ECR
  ecr_image_retention_count = 20
  backend_image_tag         = var.backend_image_tag
  worker_image_tag          = var.worker_image_tag
  frontend_image_tag        = var.frontend_image_tag

  # Secrets
  openai_api_key   = var.openai_api_key
  db_password      = var.db_password
  redis_auth_token = var.redis_auth_token

  # RDS — production: Multi-AZ, deletion protection, 30-day backups
  db_name                  = "portfolio_optimizer"
  db_username              = "portfolio_admin"
  db_instance_class        = "db.t3.medium"
  db_allocated_storage     = 50
  db_multi_az              = true
  db_deletion_protection   = true
  db_backup_retention_days = 30

  # ElastiCache — production: 2 nodes for HA
  redis_node_type       = "cache.t3.small"
  redis_num_cache_nodes = 2

  # ALB / DNS
  acm_certificate_arn = var.acm_certificate_arn
  domain_name         = var.domain_name

  # ECS Task Sizing — production: larger instances
  backend_cpu     = 1024
  backend_memory  = 2048
  worker_cpu      = 2048
  worker_memory   = 4096
  frontend_cpu    = 256
  frontend_memory = 512

  # ECS Desired Counts
  backend_desired_count  = 2
  worker_desired_count   = 2
  frontend_desired_count = 2

  # Auto-scaling
  backend_min_capacity = 2
  backend_max_capacity = 10
  worker_min_capacity  = 1
  worker_max_capacity  = 8

  # CloudWatch
  cloudwatch_log_retention_days = 90
  alarm_sns_topic_arn           = var.alarm_sns_topic_arn

  # App Config
  log_level               = "INFO"
  quantum_timeout_seconds = 60
  max_quantum_assets      = 8
  cache_ttl_seconds       = 3600
  risk_free_rate          = 0.02
}
