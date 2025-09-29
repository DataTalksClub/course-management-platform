variable "db_username" {}

variable "db_password" {}


# Amazon Aurora Database - DEV

resource "aws_rds_cluster" "dev_course_management_cluster" {
  cluster_identifier     = "dev-course-management-cluster"
  engine                 = "aurora-postgresql"
  engine_version         = "15.12"
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
