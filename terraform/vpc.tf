# VPC
resource "aws_vpc" "course_management_vpc" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "course-management"
  }
}

# Subnet
resource "aws_subnet" "course_management_subnet" {
  vpc_id     = aws_vpc.course_management_vpc.id
  cidr_block = "10.0.1.0/24"
  tags = {
    Name = "subnet"
  }
}

# Additional Subnet in a different AZ
resource "aws_subnet" "course_management_subnet_2" {
  vpc_id            = aws_vpc.course_management_vpc.id
  cidr_block        = "10.0.2.0/24" # Make sure the CIDR block does not overlap with the first subnet
  availability_zone = "eu-west-1b"
  tags = {
    Name = "subnet-2"
  }
}