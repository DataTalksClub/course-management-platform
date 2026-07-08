from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import CustomUser
from course_management.observability import record_event


@receiver(user_logged_in)
def record_user_logged_in(sender, request, user, **kwargs):
    path = getattr(request, "path", "")
    event_name = "auth.login_success"
    if path.startswith("/admin/login/user/"):
        event_name = "auth.impersonation_started"

    record_event(
        event_name,
        request=request,
        user=user,
        properties={
            "user_id": user.id,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
        },
    )


@receiver(user_logged_out)
def record_user_logged_out(sender, request, user, **kwargs):
    record_event(
        "auth.logout",
        request=request,
        user=user,
        properties={
            "user_id": user.id if user is not None else None,
        },
    )


@receiver(user_login_failed)
def record_user_login_failed(sender, credentials, request, **kwargs):
    record_event(
        "auth.login_failed",
        request=request,
        properties={
            "credential_keys": sorted(credentials.keys()),
        },
    )


@receiver(post_save, sender=CustomUser)
def record_user_created(sender, instance, created, **kwargs):
    if not created:
        return

    record_event(
        "auth.user_created",
        user=instance,
        properties={
            "user_id": instance.id,
            "is_staff": instance.is_staff,
            "is_superuser": instance.is_superuser,
        },
    )
