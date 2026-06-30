from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import CustomUser
from course_management.datamailer.sync import (
    erase_contact_from_datamailer,
    remove_enrollment_from_datamailer as remove_enrollment_recipient_list,
    remove_homework_submission_from_datamailer as remove_homework_submission_recipient_list,
    remove_project_submission_from_datamailer as remove_project_submission_recipient_list,
    remove_registration_from_datamailer as remove_registration_recipient_list,
    sync_contact,
    sync_enrollment_to_datamailer as sync_enrollment_recipient_list,
)
from courses.models import CourseRegistration, Enrollment, ProjectSubmission, Submission


@receiver(post_save, sender=CustomUser)
def sync_user_to_datamailer(sender, instance, created, **kwargs):
    if not created:
        return

    if not getattr(settings, "DATAMAILER_SYNC_ON_USER_CREATE", True):
        return

    transaction.on_commit(lambda: sync_contact(instance))


@receiver(post_delete, sender=CustomUser)
def erase_user_from_datamailer(sender, instance, **kwargs):
    user_id = instance.pk
    email = instance.email
    transaction.on_commit(
        lambda: erase_contact_from_datamailer(user_id=user_id, email=email)
    )


@receiver(post_save, sender=Enrollment)
def sync_enrollment_to_datamailer(sender, instance, created, **kwargs):
    if not created:
        return

    transaction.on_commit(
        lambda: sync_enrollment_recipient_list(instance)
    )


@receiver(post_delete, sender=CourseRegistration)
def remove_registration_from_datamailer(sender, instance, **kwargs):
    transaction.on_commit(
        lambda: remove_registration_recipient_list(instance)
    )


@receiver(post_delete, sender=Enrollment)
def remove_enrollment_from_datamailer(sender, instance, **kwargs):
    transaction.on_commit(
        lambda: remove_enrollment_recipient_list(instance)
    )


@receiver(post_delete, sender=Submission)
def remove_homework_submission_from_datamailer(sender, instance, **kwargs):
    transaction.on_commit(
        lambda: remove_homework_submission_recipient_list(instance)
    )


@receiver(post_delete, sender=ProjectSubmission)
def remove_project_submission_from_datamailer(sender, instance, **kwargs):
    transaction.on_commit(
        lambda: remove_project_submission_recipient_list(instance)
    )
