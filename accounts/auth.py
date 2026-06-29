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


def response_email(response_data):
    return response_data.get("email")


def verified_social_email(email_addresses):
    for email_address in email_addresses:
        if email_address.verified:
            return email_address.email
    return None


def sociallogin_email(sociallogin):
    if not sociallogin or not sociallogin.email_addresses:
        return None

    return (
        verified_social_email(sociallogin.email_addresses)
        or sociallogin.email_addresses[0].email
    )


def notification_email(response_data):
    return response_data.get("notification_email")


def extract_email(response_data, sociallogin=None):
    for email in (
        response_email(response_data),
        sociallogin_email(sociallogin),
        notification_email(response_data),
    ):
        if email:
            return email

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
            email = self._sociallogin_email(response_data, sociallogin)
            if not email:
                logger.info("No email found in social account data")
                return

            self._connect_sociallogin_by_email(request, sociallogin, email)
        except EmailAddress.DoesNotExist:
            logger.error(f"No user found with email {email}")
        except KeyError:
            logger.error("Email key not found in social account data")

    def _sociallogin_email(self, response_data, sociallogin):
        email = extract_email(response_data, sociallogin=sociallogin)
        logger.info(f"Extracted email {email} from OAuth response")
        return email

    def _connect_sociallogin_by_email(self, request, sociallogin, email):
        existing_emails = EmailAddress.objects.filter(email__iexact=email)
        num_existing_emails = existing_emails.count()
        logger.info(
            f"Found {num_existing_emails} existing users for email {email}"
        )

        if num_existing_emails == 0:
            user = self._create_user_for_email(email)
            sociallogin.connect(request, user)
        elif num_existing_emails == 1:
            self._connect_single_existing_user(
                request, sociallogin, email, existing_emails
            )
        else:
            self._connect_most_recent_user(
                request, sociallogin, email, existing_emails
            )

    def _create_user_for_email(self, email):
        logger.info(
            f"No existing user found with email {email}, creating a new one"
        )
        user = User.objects.create_user(
            username=email,
            email=email,
            password=generate_random_password(),
        )
        user.save()

        email_address = EmailAddress.objects.create(
            user=user,
            email=email,
            primary=True,
            verified=True,
        )
        email_address.save()
        return user

    def _connect_single_existing_user(
        self, request, sociallogin, email, existing_emails
    ):
        user = existing_emails.first().user
        logger.info(f"Found existing user with email {email}, connecting to it")
        sociallogin.connect(request, user)

    def _connect_most_recent_user(
        self, request, sociallogin, email, existing_emails
    ):
        logger.warning(
            f"Multiple users found with email {email} - attempting to link "
            "to the most recently active account."
        )
        most_recent_user = self.select_most_recent_user(existing_emails)
        if most_recent_user:
            logger.info(
                f"Found existing user with email {email}, connecting to it"
            )
            sociallogin.connect(request, most_recent_user)

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
    decorated.requires_token_auth = True
    return decorated
