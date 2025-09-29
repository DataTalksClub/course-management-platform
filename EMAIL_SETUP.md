# AWS SES Setup Instructions

## Overview
This project now supports email authentication using AWS SES (Simple Email Service) to send verification codes, similar to how Notion handles email-based sign-in.

## Environment Variables Required

Add these environment variables to your deployment:

```bash
# AWS SES Configuration
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_access_key_here
AWS_REGION=us-east-1  # or your preferred region
AWS_SES_FROM_EMAIL=noreply@yourdomain.com  # verified email in SES
```

## AWS SES Setup Steps

### 1. Create AWS SES Service
1. Go to AWS Console → SES (Simple Email Service)
2. Choose your region (recommend us-east-1)

### 2. Verify Your Domain or Email
- **For production**: Verify your domain
- **For testing**: Verify individual email addresses

#### Domain Verification:
1. Go to SES → Verified identities
2. Click "Create identity" → "Domain"
3. Enter your domain (e.g., yourdomain.com)
4. Add the required DNS records to your domain
5. Wait for verification (can take up to 72 hours)

#### Email Verification (for testing):
1. Go to SES → Verified identities  
2. Click "Create identity" → "Email address"
3. Enter the email you want to send from
4. Check your email and click the verification link

### 3. Move Out of SES Sandbox (Production)
By default, SES is in sandbox mode and can only send to verified emails.

1. Go to SES → Account dashboard
2. Click "Request production access"
3. Fill out the form with:
   - Use case: Transactional emails for user authentication
   - Website URL: Your application URL
   - Expected volume: Your estimated daily email volume
   - Bounce/complaint handling: Describe how you'll handle them

### 4. Create IAM User for SES
1. Go to IAM → Users → Create user
2. Attach policy: `AmazonSESFullAccess` (or create custom policy with minimal permissions)
3. Create access keys and use them in your environment variables

#### Minimal SES Policy:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ses:SendEmail",
                "ses:SendRawEmail"
            ],
            "Resource": "*"
        }
    ]
}
```

## Local Development
For local development, the system uses Django's console email backend, so emails will be printed to the console instead of actually being sent.

## Testing the Setup
1. Start the development server
2. Go to `/accounts/email-login/`
3. Enter an email address
4. For local development: Check console for the verification code
5. For production: Check the email inbox for the verification code

## Email Template Customization
The verification email can be customized by modifying the email content in `accounts/views.py` in the `send_verification_code` function.

## Security Features
- Verification codes expire after 10 minutes
- Only one active code per email at a time
- Codes are 6 digits and cryptographically secure
- Failed verification attempts are logged
- Rate limiting can be added for production use

## Monitoring
- Monitor SES sending quotas and bounce rates in AWS Console
- Check application logs for email sending errors
- Set up CloudWatch alarms for SES metrics if needed