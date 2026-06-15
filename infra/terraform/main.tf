################################################################################
# Portfolio Optimizer — Terraform Root Module
#
# Orchestrates all sub-modules for the AWS ECS Fargate deployment:
#   - Networking (VPC, subnets, NAT, route tables, VPC flow logs)
#   - Security Groups (all SGs in one place to avoid circular deps)
#   - ECR repositories for backend, worker, and frontend images
#   - RDS PostgreSQL 16 (Multi-AZ in production)
#   - ElastiCache Redis 7 (replication group)
#   - ECS Cluster + Fargate services (backend API, Celery worker, frontend)
#   - Application Load Balancer with HTTPS termination
#   - AWS Secrets Manager for sensitive configuration
#   - IAM roles and policies for ECS task execution
#   - CloudWatch log groups and alarms
#   - Auto-scaling policies for backend and worker services
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
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state — configure backend in each environment's backend.hcl
  # backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

################################################################################
# Locals
################################################################################

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "portfolio-optimizer"
  }

  # Availability zones — use first two in the region
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

################################################################################
# Data sources
################################################################################

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

################################################################################
# Networking
################################################################################

module "networking" {
  source = "./modules/networking"

  name_prefix          = local.name_prefix
  vpc_cidr             = var.vpc_cidr
  availability_zones   = local.azs
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  enable_nat_gateway   = var.enable_nat_gateway
  single_nat_gateway   = var.single_nat_gateway

  tags = local.common_tags
}

################################################################################
# Security Groups
# Created before all other modules to avoid circular dependencies
################################################################################

module "security_groups" {
  source = "./modules/security_groups"

  name_prefix = local.name_prefix
  vpc_id      = module.networking.vpc_id

  tags = local.common_tags
}

################################################################################
# ECR Repositories
################################################################################

module "ecr" {
  source = "./modules/ecr"

  name_prefix = local.name_prefix
  repositories = {
    backend  = "backend"
    worker   = "worker"
    frontend = "frontend"
  }
  image_retention_count = var.ecr_image_retention_count

  tags = local.common_tags
}

################################################################################
# Secrets Manager
################################################################################

module "secrets" {
  source = "./modules/secrets"

  name_prefix      = local.name_prefix
  openai_api_key   = var.openai_api_key
  db_password      = var.db_password
  redis_auth_token = var.redis_auth_token

  tags = local.common_tags
}

################################################################################
# RDS PostgreSQL
################################################################################

module "rds" {
  source = "./modules/rds"

  name_prefix            = local.name_prefix
  vpc_id                 = module.networking.vpc_id
  private_subnet_ids     = module.networking.private_subnet_ids
  rds_security_group_id  = module.security_groups.rds_sg_id
  db_name                = var.db_name
  db_username            = var.db_username
  db_password_secret_arn = module.secrets.db_password_secret_arn
  db_instance_class      = var.db_instance_class
  db_allocated_storage   = var.db_allocated_storage
  db_multi_az            = var.db_multi_az
  db_deletion_protection = var.db_deletion_protection
  db_backup_retention_days = var.db_backup_retention_days

  tags = local.common_tags
}

################################################################################
# ElastiCache Redis
################################################################################

module "elasticache" {
  source = "./modules/elasticache"

  name_prefix                 = local.name_prefix
  vpc_id                      = module.networking.vpc_id
  private_subnet_ids          = module.networking.private_subnet_ids
  redis_security_group_id     = module.security_groups.redis_sg_id
  redis_node_type             = var.redis_node_type
  redis_num_cache_nodes       = var.redis_num_cache_nodes
  redis_auth_token_secret_arn = module.secrets.redis_auth_token_secret_arn

  tags = local.common_tags
}

################################################################################
# Application Load Balancer
################################################################################

module "alb" {
  source = "./modules/alb"

  name_prefix           = local.name_prefix
  vpc_id                = module.networking.vpc_id
  public_subnet_ids     = module.networking.public_subnet_ids
  alb_security_group_id = module.security_groups.alb_sg_id
  certificate_arn       = var.acm_certificate_arn
  domain_name           = var.domain_name

  tags = local.common_tags
}

################################################################################
# IAM
################################################################################

module "iam" {
  source = "./modules/iam"

  name_prefix               = local.name_prefix
  aws_account_id            = data.aws_caller_identity.current.account_id
  aws_region                = var.aws_region
  secrets_arns              = module.secrets.all_secret_arns
  ecr_repository_arns       = module.ecr.repository_arns
  cloudwatch_log_group_arns = module.cloudwatch.log_group_arns

  tags = local.common_tags
}

################################################################################
# CloudWatch
################################################################################

module "cloudwatch" {
  source = "./modules/cloudwatch"

  name_prefix          = local.name_prefix
  log_retention_days   = var.cloudwatch_log_retention_days
  alb_arn_suffix       = module.alb.alb_arn_suffix
  backend_service_name = "${local.name_prefix}-backend"
  worker_service_name  = "${local.name_prefix}-worker"
  ecs_cluster_name     = "${local.name_prefix}-cluster"
  alarm_sns_topic_arn  = var.alarm_sns_topic_arn

  tags = local.common_tags
}

################################################################################
# ECS Cluster + Services
################################################################################

module "ecs" {
  source = "./modules/ecs"

  name_prefix                   = local.name_prefix
  vpc_id                        = module.networking.vpc_id
  private_subnet_ids            = module.networking.private_subnet_ids
  alb_target_group_backend_arn  = module.alb.target_group_backend_arn
  alb_target_group_frontend_arn = module.alb.target_group_frontend_arn

  # Pre-created security groups (avoids circular dependencies)
  backend_security_group_id  = module.security_groups.backend_sg_id
  worker_security_group_id   = module.security_groups.worker_sg_id
  frontend_security_group_id = module.security_groups.frontend_sg_id

  # ECR image URIs
  backend_image_uri  = "${module.ecr.repository_urls["backend"]}:${var.backend_image_tag}"
  worker_image_uri   = "${module.ecr.repository_urls["worker"]}:${var.worker_image_tag}"
  frontend_image_uri = "${module.ecr.repository_urls["frontend"]}:${var.frontend_image_tag}"

  # IAM
  task_execution_role_arn = module.iam.task_execution_role_arn
  task_role_arn           = module.iam.task_role_arn

  # Secrets
  openai_api_key_secret_arn   = module.secrets.openai_api_key_secret_arn
  db_password_secret_arn      = module.secrets.db_password_secret_arn
  redis_auth_token_secret_arn = module.secrets.redis_auth_token_secret_arn

  # Database
  db_host     = module.rds.db_endpoint
  db_port     = module.rds.db_port
  db_name     = var.db_name
  db_username = var.db_username

  # Redis
  redis_endpoint = module.elasticache.redis_endpoint
  redis_port     = module.elasticache.redis_port

  # CloudWatch
  cloudwatch_log_group_backend  = module.cloudwatch.log_group_backend
  cloudwatch_log_group_worker   = module.cloudwatch.log_group_worker
  cloudwatch_log_group_frontend = module.cloudwatch.log_group_frontend

  # Task sizing
  backend_cpu     = var.backend_cpu
  backend_memory  = var.backend_memory
  worker_cpu      = var.worker_cpu
  worker_memory   = var.worker_memory
  frontend_cpu    = var.frontend_cpu
  frontend_memory = var.frontend_memory

  # Desired counts
  backend_desired_count  = var.backend_desired_count
  worker_desired_count   = var.worker_desired_count
  frontend_desired_count = var.frontend_desired_count

  # Auto-scaling
  backend_min_capacity = var.backend_min_capacity
  backend_max_capacity = var.backend_max_capacity
  worker_min_capacity  = var.worker_min_capacity
  worker_max_capacity  = var.worker_max_capacity

  # App config
  environment             = var.environment
  log_level               = var.log_level
  quantum_timeout_seconds = var.quantum_timeout_seconds
  max_quantum_assets      = var.max_quantum_assets
  cache_ttl_seconds       = var.cache_ttl_seconds
  risk_free_rate          = var.risk_free_rate
  domain_name             = var.domain_name

  tags = local.common_tags
}
