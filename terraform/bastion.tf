
# Bastion Host Instance - uncomment when needed

resource "aws_instance" "bastion_host" {
  ami                    = "ami-0c0a42948ea1b4f44"
  instance_type          = "t4g.nano"
  key_name               = "razer"
  vpc_security_group_ids = [aws_security_group.public_security_group.id]

  subnet_id = aws_subnet.course_management_public_subnet.id

  # associate_public_ip_address = true

  tags = {
    Name = "Course Management Bastion Host"
  }
}

output "bastion_host_public_dns" {
  value       = aws_instance.bastion_host.public_ip
  description = "The public DNS name of the Bastion Host"
}
