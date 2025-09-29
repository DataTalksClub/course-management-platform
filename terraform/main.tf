variable "region" {
  default = "eu-west-1"
  description = "the AWS region"
}

variable "ses_domain" {
  description = "Domain for SES email sending (e.g., yourdomain.com)"
  type        = string
  default     = "datatalks.club"
}

variable "ses_test_email" {
  description = "Test email address for SES verification (for testing only)"
  type        = string
  default     = "noreply@datatalks.club"
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}
