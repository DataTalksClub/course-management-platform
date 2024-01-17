variable "region" {
  default = "eu-west-1"
  description = "the AWS region"
}

provider "aws" {
  region = var.region
}

