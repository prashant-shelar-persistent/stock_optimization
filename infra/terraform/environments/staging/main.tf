################################################################################
# Staging Environment — Terraform Configuration
#
# Staging mirrors production topology but uses smaller/cheaper instances
# and a single NAT Gateway to reduce cost.
#
# Usage:
#   cd infra/terraform/environments/staging
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

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "portfolio-optimizer"
      Environment = "staging"
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
  environment  = "staging"
  aws_region   = var.aws_region

  # Networking — staging uses single NAT to save cost
  vpc_cidr             = "10.1.0.0/16"
  public_subnet_cidrs  = ["10.1.1.0/24", "10.1.2.0/24"]
  private_subnet_cidrs = ["10.1.10.0/24", "10.1.11.0/24"]
  enable_nat_gateway   = true
  single_nat_gateway   = true # Cost saving for staging

  # ECR
  ecr_image_retention_count = 10
  backend_image_tag         = var.backend_image_tag
  worker_image_tag          = var.worker_image_tag
  frontend_image_tag        = var.frontend_image_tag

  # Secrets
  openai_api_key   = var.openai_api_key
  db_password      = var.db_password
  redis_auth_token = var.redis_auth_token

  # RDS — staging: single-AZ, no deletion protection
  db_name                  = "portfolio_optimizer_staging"
  db_username              = "portfolio_admin"
  db_instance_class        = "db.t3.small"
  db_allocated_storage     = 20
  db_multi_az              = false
  db_deletion_protection   = false
  db_backup_retention_days = 7

  # ElastiCache — staging: single node
  redis_node_type       = "cache.t3.micro"
  redis_num_cache_nodes = 1

  # ALB / DNS
  acm_certificate_arn = var.acm_certificate_arn
  domain_name         = var.domain_name

  # ECS Task Sizing — staging: smaller instances
  backend_cpu     = 512
  backend_memory  = 1024
  worker_cpu      = 1024
  worker_memory   = 2048
  frontend_cpu    = 256
  frontend_memory = 512

  # ECS Desired Counts — staging: minimal replicas
  backend_desired_count  = 1
  worker_desired_count   = 1
  frontend_desired_count = 1

  # Auto-scaling — staging: minimal range
  backend_min_capacity = 1
  backend_max_capacity = 4
  worker_min_capacity  = 1
  worker_max_capacity  = 3

  # CloudWatch
  cloudwatch_log_retention_days = 14
  alarm_sns_topic_arn           = var.alarm_sns_topic_arn

  # App Config
  log_level               = "DEBUG"
  quantum_timeout_seconds = 120 # More lenient for testing
  max_quantum_assets      = 8
  cache_ttl_seconds       = 300 # Shorter TTL for testing
  risk_free_rate          = 0.02
}
