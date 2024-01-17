variable "db_username" {}

variable "db_password" {}


# Security Group for the Aurora Database
resource "aws_security_group" "db_security_group" {
  name_prefix = "db-sg-"
  description = "Security group for the Aurora database"
  vpc_id      = aws_vpc.course_management_vpc.id

  # Allow all traffic within the VPC
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.course_management_vpc.cidr_block]
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
  name       = "db-subnet-group"
  subnet_ids = [aws_subnet.course_management_subnet.id, aws_subnet.course_management_subnet_2.id]

  tags = {
    Name = "db-subnet-group"
  }
}


# Amazon Aurora Database - DEV

resource "aws_rds_cluster" "dev_course_management_cluster" {
  cluster_identifier     = "dev-course-management-cluster"
  engine                 = "aurora-postgresql"
  engine_version         = "15.4"
  database_name          = "coursemanagement"
  master_username        = var.db_username
  master_password        = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.course_management_subnet_group.name
  vpc_security_group_ids = [aws_security_group.db_security_group.id]

  skip_final_snapshot = true
}

resource "aws_rds_cluster_instance" "dev_course_management_instances" {
  count              = 1
  identifier         = "course-management-instance-${count.index}"
  cluster_identifier = aws_rds_cluster.dev_course_management_cluster.id
  instance_class     = "db.t3.medium"
  engine             = "aurora-postgresql"
}
