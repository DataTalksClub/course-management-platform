
resource "aws_subnet" "course_management_public_subnet" {
  vpc_id                  = aws_vpc.course_management_vpc.id
  cidr_block              = "10.0.3.0/24" # Adjust CIDR block as needed
  map_public_ip_on_launch = true          # Enable auto-assign public IP

  availability_zone = "${var.region}a"

  tags = {
    Name = "course-management-public-subnet"
  }
}

resource "aws_subnet" "course_management_public_subnet_2" {
  vpc_id                  = aws_vpc.course_management_vpc.id
  cidr_block              = "10.0.4.0/24" # Adjust CIDR block as needed
  map_public_ip_on_launch = true          # Enable auto-assign public IP

  availability_zone = "${var.region}b"

  tags = {
    Name = "course-management-public-subnet"
  }
}


# Ensure there's a route to an Internet Gateway
resource "aws_internet_gateway" "course_management_gateway" {
  vpc_id = aws_vpc.course_management_vpc.id
}

resource "aws_route_table" "public_route_table" {
  vpc_id = aws_vpc.course_management_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.course_management_gateway.id
  }
}

resource "aws_route_table_association" "public_subnet_association" {
  subnet_id      = aws_subnet.course_management_public_subnet.id
  route_table_id = aws_route_table.public_route_table.id
}

resource "aws_route_table_association" "public_subnet_association_2" {
  subnet_id      = aws_subnet.course_management_public_subnet_2.id
  route_table_id = aws_route_table.public_route_table.id
}

# Security Group for Bastion Host
resource "aws_security_group" "public_security_group" {
  name        = "public-course-management-sg"
  description = "Security Group for Bastion Host"
  vpc_id      = aws_vpc.course_management_vpc.id

  ingress {
    description = "SSH from the Internet"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["2.210.86.190/32", "212.204.40.18/32"]
  }

  # uncomment to allow access from everywhere
  # ingress {
  #   description = "SSH from the Internet"
  #   from_port   = 22
  #   to_port     = 22
  #   protocol    = "tcp"
  #   cidr_blocks = ["0.0.0.0/0"]
  # }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "public-course-management-sg"
  }
}