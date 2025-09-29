# IAM user for AWS SES email functionality
resource "aws_iam_user" "ses_email_user" {
  name = "course-management-ses-email-user"
  
  tags = {
    Name        = "Course Management SES Email User"
    Purpose     = "Email verification and notifications"
    Environment = "all"
  }
}

# Access key for the SES user
# resource "aws_iam_access_key" "ses_email_user_key" {
#   user = aws_iam_user.ses_email_user.name
# }

# IAM policy for SES email sending permissions
resource "aws_iam_user_policy" "ses_email_policy" {
  name = "ses-email-policy"
  user = aws_iam_user.ses_email_user.name

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "ses:GetSendQuota",
          "ses:GetSendStatistics",
          "ses:ListIdentities",
          "ses:GetIdentityDkimAttributes",
          "ses:GetIdentityVerificationAttributes"
        ],
        Resource = "*"
      }
    ]
  })
}

# SES email identity for initial testing (replace with your verified email)
resource "aws_ses_email_identity" "test_email" {
  count = var.ses_test_email != "" ? 1 : 0
  email = var.ses_test_email
}

# SES domain identity (optional, for production use)
resource "aws_ses_domain_identity" "course_management_domain" {
  count  = var.ses_domain != "" ? 1 : 0
  domain = var.ses_domain
}

# SES domain DKIM (only if domain is configured)
resource "aws_ses_domain_dkim" "course_management_dkim" {
  count  = var.ses_domain != "" ? 1 : 0
  domain = aws_ses_domain_identity.course_management_domain[0].domain
}

# SES domain mail from (only if domain is configured)
resource "aws_ses_domain_mail_from" "course_management_mail_from" {
  count            = var.ses_domain != "" ? 1 : 0
  domain           = aws_ses_domain_identity.course_management_domain[0].domain
  mail_from_domain = "mail.${aws_ses_domain_identity.course_management_domain[0].domain}"
}

# SES configuration set for tracking
resource "aws_ses_configuration_set" "course_management_config_set" {
  name = "course-management-email-config"

  delivery_options {
    tls_policy = "Require"
  }

  reputation_metrics_enabled = true
}

# Outputs for the SES user credentials
# output "ses_user_access_key_id" {
#   value       = aws_iam_access_key.ses_email_user_key.id
#   description = "Access key ID for SES email user"
# }

# output "ses_user_secret_access_key" {
#   value       = aws_iam_access_key.ses_email_user_key.secret
#   sensitive   = true
#   description = "Secret access key for SES email user"
# }

# Conditional outputs for domain configuration
output "ses_domain_identity_arn" {
  value       = var.ses_domain != "" ? aws_ses_domain_identity.course_management_domain[0].arn : null
  description = "ARN of the SES domain identity (if configured)"
}

output "ses_domain_verification_token" {
  value       = var.ses_domain != "" ? aws_ses_domain_identity.course_management_domain[0].verification_token : null
  description = "Domain verification token for DNS setup (if configured)"
}

output "ses_dkim_tokens" {
  value       = var.ses_domain != "" ? aws_ses_domain_dkim.course_management_dkim[0].dkim_tokens : null
  description = "DKIM tokens for DNS setup (if configured)"
}

output "ses_mail_from_domain" {
  value       = var.ses_domain != "" ? aws_ses_domain_mail_from.course_management_mail_from[0].mail_from_domain : null
  description = "Mail from domain for SES (if configured)"
}

# Output for test email
output "ses_test_email_identity" {
  value       = var.ses_test_email != "" ? aws_ses_email_identity.test_email[0].email : null
  description = "Test email identity for SES (if configured)"
}