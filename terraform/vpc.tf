# VPC
resource "aws_vpc" "course_management_vpc" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "course-management"
  }
}
