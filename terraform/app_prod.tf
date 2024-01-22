resource "aws_cloudwatch_log_group" "couse_management_logs_prod" {
  name              = "/ecs/course-management-prod"
  retention_in_days = 7

  tags = {
    Name        = "ECS Course Management Logs"
    Environment = "Production"
    # Add additional tags as needed
  }
}

resource "aws_ecs_task_definition" "course_management_task_prod" {
  family                   = "course-management-prod"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256" # Adjust as needed
  memory                   = "512" # Adjust as needed
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([{
    name  = "course-management-prod",
    image = "${aws_ecr_repository.course_management_ecr_repo.repository_url}:${var.prod_tag}",
    portMappings = [{
      containerPort = 80,
      hostPort      = 80
    }],
    environment = [
      {
        name  = "DEBUG",
        value = "0"
      },
      {
        name  = "DATABASE_URL",
        value = "postgresql://${var.db_username}:${var.db_password}@${aws_rds_cluster.dev_course_management_cluster.endpoint}:${aws_rds_cluster.dev_course_management_cluster.port}/prod"
      },
      {
        NAME  = "SECRET_KEY",
        value = var.django_key
      },
      {
        name = "EXTRA_ALLOWED_HOSTS",
        value = "courses.datatalks.club,${aws_lb.course_managemenent_alb_prod.dns_name}"
      },
      {
        NAME = "VERSION",
        value = var.prod_tag
      }
    ],
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.couse_management_logs_prod.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "course_management_service_prod" {
  name    = "course-management-prod"
  cluster = aws_ecs_cluster.course_management_cluster.id

  task_definition = aws_ecs_task_definition.course_management_task_prod.arn
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = [aws_subnet.course_management_subnet.id, aws_subnet.course_management_subnet_2.id]
    security_groups = [aws_security_group.db_security_group.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.course_management_tg_prod.arn
    container_name   = "course-management-prod"
    container_port   = 80
  }

  desired_count = 1

  lifecycle {
    ignore_changes = [
      desired_count,
      task_definition, # updated via CI/CD
      // Other attributes that Terraform should not update.
    ]
  }
}

resource "aws_lb" "course_managemenent_alb_prod" {
  name               = "course-management-prod"
  internal           = false
  load_balancer_type = "application"

  security_groups = [aws_security_group.course_management_sg.id]
  subnets         = [aws_subnet.course_management_public_subnet.id, aws_subnet.course_management_public_subnet_2.id]

  enable_deletion_protection = false
}

resource "aws_lb_target_group" "course_management_tg_prod" {
  name     = "course-management-prod"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.course_management_vpc.id

  target_type = "ip"

  health_check {
    enabled = true
    path    = "/ping"
  }
}

resource "aws_lb_listener" "course_managemenent_listener_prod" {
  load_balancer_arn = aws_lb.course_managemenent_alb_prod.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "course_managemenent_https_listener_prod" {
  load_balancer_arn = aws_lb.course_managemenent_alb_prod.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.course_management_tg_prod.arn
  }
}

resource "aws_route53_record" "subdomain_alias_prod" {
  zone_id = "Z00653771YEUL1BFHEDFR"
  name    = "courses.datatalks.club"
  type    = "A" # Alias

  alias {
    name                   =   aws_lb.course_managemenent_alb_prod.dns_name
    zone_id                = aws_lb.course_managemenent_alb_prod.zone_id
    evaluate_target_health = true
  }
}

output "alb_prod_dns_name" {
  value       = aws_lb.course_managemenent_alb_prod.dns_name
  description = "The DNS name of the prod application load balancer"
}
