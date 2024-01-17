# ECR

resource "aws_ecr_repository" "course_management_ecr_repo" {
  name = "course-management"

  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}


# ECS Cluster

resource "aws_ecs_cluster" "course_management_cluster" {
  name = "course-management-cluster"
}

resource "aws_iam_role" "ecs_execution_role" {
  name = "ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        },
      },
    ],
  })
}


resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy_attachment" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
  # permissions:
  # "ecr:GetAuthorizationToken",
  # "ecr:BatchCheckLayerAvailability",
  # "ecr:GetDownloadUrlForLayer",
  # "ecr:BatchGetImage",
  # "logs:CreateLogStream",
  # "logs:PutLogEvents"
}

resource "aws_security_group" "course_management_sg" {
  name        = "course-management-alb-sg"
  description = "Security Group for ALB"
  vpc_id      = aws_vpc.course_management_vpc.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}