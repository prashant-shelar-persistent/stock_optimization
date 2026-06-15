################################################################################
# IAM Module — ECS Task Execution and Task Roles
#
# task_execution_role: Used by ECS agent to pull images, write logs, and
#                      retrieve secrets from Secrets Manager.
# task_role:           Used by the running container for application-level
#                      AWS API calls (e.g., Secrets Manager reads at runtime).
################################################################################

################################################################################
# ECS Task Execution Role
# (Assumed by the ECS agent — NOT the container itself)
################################################################################

resource "aws_iam_role" "task_execution" {
  name        = "${var.name_prefix}-ecs-task-execution-role"
  description = "ECS task execution role for ${var.name_prefix} — allows ECS agent to pull images and write logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ECSTasksAssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

# Attach the AWS-managed ECS task execution policy (ECR pull + CloudWatch logs)
resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Custom policy: allow reading secrets from Secrets Manager
resource "aws_iam_policy" "secrets_read" {
  name        = "${var.name_prefix}-secrets-read-policy"
  description = "Allow ECS task execution role to read secrets from Secrets Manager"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = var.secrets_arns
      },
      {
        Sid    = "DecryptSecrets"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "task_execution_secrets" {
  role       = aws_iam_role.task_execution.name
  policy_arn = aws_iam_policy.secrets_read.arn
}

# Custom policy: allow pulling from ECR (belt-and-suspenders alongside managed policy)
resource "aws_iam_policy" "ecr_pull" {
  name        = "${var.name_prefix}-ecr-pull-policy"
  description = "Allow ECS task execution role to pull images from ECR"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRGetAuthToken"
        Effect = "Allow"
        Action = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "ECRPullImages"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = var.ecr_repository_arns
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "task_execution_ecr" {
  role       = aws_iam_role.task_execution.name
  policy_arn = aws_iam_policy.ecr_pull.arn
}

# Custom policy: allow writing to CloudWatch Logs
resource "aws_iam_policy" "cloudwatch_logs" {
  name        = "${var.name_prefix}-cloudwatch-logs-policy"
  description = "Allow ECS tasks to write to CloudWatch Logs"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "CloudWatchLogs"
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ]
      Resource = [for arn in var.cloudwatch_log_group_arns : "${arn}:*"]
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "task_execution_logs" {
  role       = aws_iam_role.task_execution.name
  policy_arn = aws_iam_policy.cloudwatch_logs.arn
}

################################################################################
# ECS Task Role
# (Assumed by the running container for application-level AWS API calls)
################################################################################

resource "aws_iam_role" "task" {
  name        = "${var.name_prefix}-ecs-task-role"
  description = "ECS task role for ${var.name_prefix} — used by running containers"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ECSTasksAssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        ArnLike = {
          "aws:SourceArn" = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:*"
        }
      }
    }]
  })

  tags = var.tags
}

# Allow containers to read secrets at runtime (for dynamic secret refresh)
resource "aws_iam_role_policy_attachment" "task_secrets" {
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.secrets_read.arn
}

# Allow containers to write CloudWatch Logs
resource "aws_iam_role_policy_attachment" "task_logs" {
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.cloudwatch_logs.arn
}

# Allow ECS Exec (for debugging in non-production)
resource "aws_iam_policy" "ecs_exec" {
  name        = "${var.name_prefix}-ecs-exec-policy"
  description = "Allow ECS Exec for interactive debugging"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ECSExec"
      Effect = "Allow"
      Action = [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ]
      Resource = "*"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "task_ecs_exec" {
  role       = aws_iam_role.task.name
  policy_arn = aws_iam_policy.ecs_exec.arn
}
