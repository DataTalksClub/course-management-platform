
# ECR

resource "aws_ecr_repository" "course_management_ecr_repo" {
  name = "course-management" # Repository name

  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}


# ECS Cluster

resource "aws_ecs_cluster" "dev_course_management_cluster" {
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
}


resource "aws_ecs_task_definition" "dev_course_management_task" {
  family                   = "course-management"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256" # Adjust as needed
  memory                   = "512" # Adjust as needed
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([{
    name  = "dev-course-management-container",
    image = "${aws_ecr_repository.course_management_ecr_repo.repository_url}:latest",
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
      }
      // Add more environment variables as needed
    ],
    // Additional container settings...
  }])
}

resource "aws_ecs_service" "dev_course_management_service" {
  name    = "dev_course-management-service"
  cluster = aws_ecs_cluster.dev_course_management_cluster.id

  task_definition = aws_ecs_task_definition.dev_course_management_task.arn
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = [aws_subnet.course_management_subnet.id, aws_subnet.course_management_subnet_2.id]
    security_groups = [aws_security_group.db_security_group.id]
  }

  desired_count = 1 # Adjust as needed

  lifecycle {
    ignore_changes = [
      desired_count,
      // Other attributes that Terraform should not update.
    ]
  }
}
