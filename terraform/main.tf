variable "region" {
  default = "eu-west-1"
  description = "the AWS region"
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}
