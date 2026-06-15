################################################################################
# ALB Module — Application Load Balancer
#
# Creates:
#   - Application Load Balancer (internet-facing)
#   - Target groups for backend (port 8000) and frontend (port 80)
#   - HTTP listener (redirects to HTTPS if cert provided, else forwards)
#   - HTTPS listener with routing rules (if ACM cert provided)
#
# Note: The ALB security group is created in the security_groups module
#       and passed in via var.alb_security_group_id to avoid circular deps.
################################################################################

################################################################################
# Application Load Balancer
################################################################################

resource "aws_lb" "main" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.enable_deletion_protection
  enable_http2               = true
  idle_timeout               = 60

  access_logs {
    bucket  = var.access_logs_bucket != "" ? var.access_logs_bucket : ""
    prefix  = var.name_prefix
    enabled = var.access_logs_bucket != ""
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-alb"
  })
}

################################################################################
# Target Groups
################################################################################

resource "aws_lb_target_group" "backend" {
  name        = "${var.name_prefix}-backend-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # Required for Fargate

  health_check {
    enabled             = true
    path                = "/api/v1/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200,307"
  }

  deregistration_delay = 30

  stickiness {
    type    = "lb_cookie"
    enabled = false
  }

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-backend-tg"
    Service = "backend"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_target_group" "frontend" {
  name        = "${var.name_prefix}-frontend-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-frontend-tg"
    Service = "frontend"
  })

  lifecycle {
    create_before_destroy = true
  }
}

################################################################################
# HTTP Listener
################################################################################

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # If HTTPS cert is provided, redirect HTTP → HTTPS; otherwise forward to frontend
  dynamic "default_action" {
    for_each = var.certificate_arn != "" ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }

  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.frontend.arn
    }
  }

  tags = var.tags
}

################################################################################
# HTTPS Listener (conditional on ACM certificate)
################################################################################

resource "aws_lb_listener" "https" {
  count = var.certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  tags = var.tags
}

################################################################################
# Listener Rules — Route /api/* and /ws/* to backend
################################################################################

resource "aws_lb_listener_rule" "backend_api" {
  # Attach to HTTPS listener if available, otherwise HTTP
  listener_arn = var.certificate_arn != "" ? aws_lb_listener.https[0].arn : aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/ws/*", "/health", "/metrics", "/docs", "/redoc", "/openapi.json"]
    }
  }

  tags = var.tags
}
