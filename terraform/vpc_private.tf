

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
  availability_zone = "${var.region}b"
  tags = {
    Name = "subnet-2"
  }
}

# NAT to allow private instances to access the internet

resource "aws_eip" "nat_eip" {
  domain = "vpc"
}

resource "aws_nat_gateway" "nat_gateway" {
  allocation_id = aws_eip.nat_eip.id
  subnet_id     = aws_subnet.course_management_public_subnet.id
}

resource "aws_route_table" "private_route_table" {
  vpc_id = aws_vpc.course_management_vpc.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat_gateway.id
  }
}

resource "aws_route_table_association" "private_subnet_association" {
  subnet_id      = aws_subnet.course_management_subnet.id
  route_table_id = aws_route_table.private_route_table.id
}

resource "aws_route_table_association" "private_subnet_association_2" {
  subnet_id      = aws_subnet.course_management_subnet_2.id
  route_table_id = aws_route_table.private_route_table.id
}

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
