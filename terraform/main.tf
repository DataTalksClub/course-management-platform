provider "aws" {
  region = "eu-west-1"
}

variable "environment" {
  description = "The environment (dev or prod)"
  default     = "dev"
}

variable "db_username" {}

variable "db_password" {}

locals {
  name_prefix = var.environment == "prod" ? "prod" : "dev"
}

# VPC
resource "aws_vpc" "course_management_vpc" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "${local.name_prefix}-course-management"
  }
}

# Subnet
resource "aws_subnet" "course_management_subnet" {
  vpc_id     = aws_vpc.course_management_vpc.id
  cidr_block = "10.0.1.0/24"
  tags = {
    Name = "${local.name_prefix}-subnet"
  }
}

# Additional Subnet in a different AZ
resource "aws_subnet" "course_management_subnet_2" {
  vpc_id            = aws_vpc.course_management_vpc.id
  cidr_block        = "10.0.2.0/24" # Make sure the CIDR block does not overlap with the first subnet
  availability_zone = "eu-west-1b"  # Change to a different AZ
  tags = {
    Name = "${local.name_prefix}-subnet-2"
  }
}

# Security Group for the Aurora Database
resource "aws_security_group" "db_security_group" {
  name_prefix = "${local.name_prefix}-db-sg-"
  description = "Security group for the Aurora database"
  vpc_id      = aws_vpc.course_management_vpc.id

  # Allow all traffic within the VPC
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.course_management_vpc.cidr_block]
  }

  # Allow all traffic from your laptop's IP
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["2.212.13.245/32"] # Replace with your laptop's public IP address
  }

  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# DB Subnet Group
resource "aws_db_subnet_group" "course_management_subnet_group" {
  name       = "${local.name_prefix}-db-subnet-group"
  subnet_ids = [aws_subnet.course_management_subnet.id, aws_subnet.course_management_subnet_2.id]

  tags = {
    Name = "${local.name_prefix}-db-subnet-group"
  }
}



# Amazon Aurora Database

resource "aws_rds_cluster" "course_management_cluster" {
  cluster_identifier     = "${local.name_prefix}-course-management-cluster"
  engine                 = "aurora-postgresql"
  engine_version         = "15.4"
  database_name          = "coursemanagement"
  master_username        = var.db_username
  master_password        = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.course_management_subnet_group.name
  vpc_security_group_ids = [aws_security_group.db_security_group.id]
}

resource "aws_rds_cluster_instance" "course_management_instances" {
  count              = 1 # Adjust as needed
  identifier         = "${local.name_prefix}-course-management-instance-${count.index}"
  cluster_identifier = aws_rds_cluster.course_management_cluster.id
  instance_class     = "db.t3.medium"
  engine             = "aurora-postgresql"
}


# ECR

resource "aws_ecr_repository" "course_management_ecr_repo" {
  name = "${local.name_prefix}-course-management-repo" # Repository name

  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}




# ECS Cluster

resource "aws_ecs_cluster" "course_management_cluster" {
  name = "${local.name_prefix}-course-management-cluster"
}

resource "aws_iam_role" "ecs_execution_role" {
  name = "${local.name_prefix}-ecs-execution-role"

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


resource "aws_ecs_task_definition" "course_management_task" {
  family                   = "${local.name_prefix}-course-management"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256" # Adjust as needed
  memory                   = "512" # Adjust as needed
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([{
    name  = "course-management-container",
    image = "${aws_ecr_repository.course_management_ecr_repo.repository_url}:latest",
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
        value = "postgresql://${var.db_username}:${var.db_password}@${aws_rds_cluster.course_management_cluster.endpoint}:${aws_rds_cluster.course_management_cluster.port}/${aws_rds_cluster.course_management_cluster.database_name}"
      }
      // Add more environment variables as needed
    ],
    // Additional container settings...
  }])
}

resource "aws_ecs_service" "course_management_service" {
  name    = "${local.name_prefix}-course-management-service"
  cluster = aws_ecs_cluster.course_management_cluster.id

  task_definition = aws_ecs_task_definition.course_management_task.arn
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
