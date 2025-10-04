import json
import logging
from functools import wraps

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.models import EmailAddress

from django.utils.crypto import get_random_string

from django.contrib.auth import get_user_model

from django.http import JsonResponse

from .models import Token


User = get_user_model()

logger = logging.getLogger(__name__)


def generate_random_password(
    length=12,
    allowed_chars="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
):
    return get_random_string(
        length=length, allowed_chars=allowed_chars
    )


def extract_email(response_data, sociallogin=None):
    if response_data.get("email"):
        return response_data["email"]

    # GitHub-specific (via allauth fetch)
    if sociallogin and sociallogin.email_addresses:
        verified = [e for e in sociallogin.email_addresses if e.verified]
        if verified:
            return verified[0].email
        return sociallogin.email_addresses[0].email

    if response_data.get("notification_email"):
        return response_data["notification_email"]

    raise KeyError("Email not found in response data")


class ConsolidatingSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        response_data = sociallogin.account.extra_data
        logger.info(f"OAuth response: {json.dumps(response_data)}")

        if sociallogin.is_existing:
            logger.info(
                f"Social login already exists for {sociallogin.user}"
            )
            return

        email = None
        try:
            email = extract_email(response_data, sociallogin=sociallogin)
            logger.info(f"Extracted email {email} from OAuth response")
            if email is None or len(email) == 0:
                logger.info("No email found in social account data")
                return

            existing_emails = EmailAddress.objects.filter(
                email__iexact=email
            )
            num_existing_emails = existing_emails.count()
            logger.info(f"Found {num_existing_emails} existing users for email {email}")

            if num_existing_emails == 0:
                # No existing user with this email, so create a new one
                logger.info(
                    f"No existing user found with email {email}, creating a new one"
                )

                password = generate_random_password()
                user = User.objects.create_user(
                    username=email, email=email, password=password
                )
                user.save()

                email_address = EmailAddress.objects.create(
                    user=user,
                    email=email,
                    primary=True,
                    verified=True,
                )

                email_address.save()

                # Link the new social login to the new user
                sociallogin.connect(request, user)

            if num_existing_emails == 1:
                # Link the new social login to the existing user
                first_email = existing_emails.first()
                user = first_email.user

                logger.info(
                    f"Found existing user with email {email}, connecting to it"
                )
                sociallogin.connect(request, user)

            if num_existing_emails > 1:
                # Multiple users found with the same email
                logger.warning(
                    f"Multiple users found with email {email} - attempting to link to the most recently active account."
                )
                # Logic to select the most recently active account
                most_recent_user = self.select_most_recent_user(
                    existing_emails
                )
                if most_recent_user:
                    logger.info(
                        f"Found existing user with email {email}, connecting to it"
                    )
                    sociallogin.connect(request, most_recent_user)

        except EmailAddress.DoesNotExist:
            logger.error(f"No user found with email {email}")
        except KeyError:
            logger.error("Email key not found in social account data")

    @staticmethod
    def select_most_recent_user(email_addresses):
        # Assuming 'last_login' can be used to determine the most recently active user
        users = [
            email.user for email in email_addresses if email.user
        ]
        return max(
            users,
            key=lambda user: (user.last_login or user.date_joined),
            default=None,
        )




def token_required(f):
    @wraps(f)
    def decorated(request, *args, **kwargs):
        token_key = request.headers.get('Authorization')
        if token_key:
            token_key = token_key.replace('Token ', '', 1)  # Assuming the token is sent as "Token <token_key>"
            try:
                token = Token.objects.get(key=token_key)
                request.user = token.user
            except Token.DoesNotExist:
                return JsonResponse({'error': 'Invalid token'}, status=401)
        else:
            return JsonResponse({'error': 'Authentication token required'}, status=401)

        return f(request, *args, **kwargs)
    return decorated