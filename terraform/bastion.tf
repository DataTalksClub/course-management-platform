
resource "aws_subnet" "course_management_public_subnet" {
  vpc_id                  = aws_vpc.course_management_vpc.id
  cidr_block              = "10.0.3.0/24" # Adjust CIDR block as needed
  map_public_ip_on_launch = true          # Enable auto-assign public IP

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


# Security Group for Bastion Host
resource "aws_security_group" "bastion_sg" {
  name        = "bastion-sg"
  description = "Security Group for Bastion Host"
  vpc_id      = aws_vpc.course_management_vpc.id

  ingress {
    description = "SSH from the Internet"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["2.212.13.245/32"]
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
    Name = "bastion-sg"
  }
}

# Bastion Host Instance
resource "aws_instance" "bastion_host" {
  ami                    = "ami-0c0a42948ea1b4f44"
  instance_type          = "t4g.nano"
  key_name               = "razer"
  vpc_security_group_ids = [aws_security_group.bastion_sg.id]

  subnet_id = aws_subnet.course_management_public_subnet.id

  associate_public_ip_address = true

  tags = {
    Name = "Course Management Bastion Host"
  }
}

resource "aws_ec2_instance_state" "bastion_host_state" {
  instance_id = aws_instance.bastion_host.id
  # change to "running" to start the instance
  state       = "stopped"
}

output "bastion_host_public_dns" {
  value       = aws_instance.bastion_host.public_ip
  description = "The public DNS name of the Bastion Host"
}
