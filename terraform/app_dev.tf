resource "aws_cloudwatch_log_group" "couse_management_logs_dev" {
  name              = "/ecs/course-management-dev"
  retention_in_days = 7

  tags = {
    Name        = "ECS Course Management Logs"
    Environment = "Development"
    # Add additional tags as needed
  }
}

resource "aws_ecs_task_definition" "dev_course_management_task" {
  family                   = "course-management-dev"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256" # Adjust as needed
  memory                   = "512" # Adjust as needed
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([{
    name  = "course-management-dev",
    image = "${aws_ecr_repository.course_management_ecr_repo.repository_url}:${var.dev_tag}",
    portMappings = [{
      containerPort = 80,
      hostPort      = 80
    }],
    environment = [
      {
        name  = "DEBUG",
        value = "1"
      },
      {
        name  = "DATABASE_URL",
        value = "postgresql://${var.db_username}:${var.db_password}@${aws_rds_cluster.dev_course_management_cluster.endpoint}:${aws_rds_cluster.dev_course_management_cluster.port}/dev"
      },
      {
        NAME  = "SECRET_KEY",
        value = var.django_key
      },
      {
        name = "EXTRA_ALLOWED_HOSTS",
        value = "dev.courses.datatalks.club,${aws_lb.course_managemenent_alb_dev.dns_name}"
      },
      {
        NAME = "VERSION",
        value = var.dev_tag
      }
    ],
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.couse_management_logs_dev.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "course_management_service_dev" {
  name    = "course-management-dev"
  cluster = aws_ecs_cluster.course_management_cluster.id

  task_definition = aws_ecs_task_definition.dev_course_management_task.arn
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = [aws_subnet.course_management_subnet.id, aws_subnet.course_management_subnet_2.id]
    security_groups = [aws_security_group.db_security_group.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.course_management_tg_dev.arn
    container_name   = "course-management-dev"
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

resource "aws_lb" "course_managemenent_alb_dev" {
  name               = "course-management-dev"
  internal           = false
  load_balancer_type = "application"

  security_groups = [aws_security_group.course_management_sg.id]
  subnets         = [aws_subnet.course_management_public_subnet.id, aws_subnet.course_management_public_subnet_2.id]

  enable_deletion_protection = false
}

resource "aws_lb_target_group" "course_management_tg_dev" {
  name     = "course-management-dev"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.course_management_vpc.id

  target_type = "ip"

  health_check {
    enabled = true
    path    = "/ping"
  }
}

resource "aws_lb_listener" "course_managemenent_listener_dev" {
  load_balancer_arn = aws_lb.course_managemenent_alb_dev.arn
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

resource "aws_lb_listener" "course_managemenent_https_listener_dev" {
  load_balancer_arn = aws_lb.course_managemenent_alb_dev.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.course_management_tg_dev.arn
  }
}

resource "aws_route53_record" "dev_subdomain_cname" {
  zone_id = "Z00653771YEUL1BFHEDFR"
  name    = "dev.courses.datatalks.club"
  type    = "CNAME"

  ttl = 1800 # in seconds

  records = [aws_lb.course_managemenent_alb_dev.dns_name]
}

output "alb_dev_dns_name" {
  value       = aws_lb.course_managemenent_alb_dev.dns_name
  description = "The DNS name of the dev application load balancer"
}
