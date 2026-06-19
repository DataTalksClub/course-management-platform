from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import CustomUser
from course_management.datamailer import (
    sync_contact,
    sync_enrollment_to_datamailer as sync_enrollment_recipient_list,
)
from courses.models import Enrollment


@receiver(post_save, sender=CustomUser)
def sync_user_to_datamailer(sender, instance, created, **kwargs):
    if not created:
        return

    if not getattr(settings, "DATAMAILER_SYNC_ON_USER_CREATE", True):
        return

    transaction.on_commit(lambda: sync_contact(instance))


@receiver(post_save, sender=Enrollment)
def sync_enrollment_to_datamailer(sender, instance, created, **kwargs):
    if not created:
        return

    transaction.on_commit(
        lambda: sync_enrollment_recipient_list(instance)
    )
