from functools import partial

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import CustomUser
from course_management.datamailer.sync.contacts import (
    erase_contact_from_datamailer,
    sync_contact,
)
from course_management.datamailer.sync.membership_removals import (
    remove_enrollment_from_datamailer as remove_enrollment_recipient_list,
    remove_homework_submission_from_datamailer as remove_homework_submission_recipient_list,
    remove_project_submission_from_datamailer as remove_project_submission_recipient_list,
    remove_registration_from_datamailer as remove_registration_recipient_list,
)
from course_management.datamailer.sync.memberships import (
    sync_enrollment_to_datamailer as sync_enrollment_recipient_list,
)
from courses.models.course import CourseRegistration, Enrollment
from courses.models.homework import Submission
from courses.models.project import ProjectSubmission


@receiver(post_save, sender=CustomUser)
def sync_user_to_datamailer(sender, instance, created, **kwargs):
    if not created:
        return

    if not getattr(settings, "DATAMAILER_SYNC_ON_USER_CREATE", True):
        return

    callback = partial(sync_contact, instance)
    transaction.on_commit(callback)


@receiver(post_delete, sender=CustomUser)
def erase_user_from_datamailer(sender, instance, **kwargs):
    user_id = instance.pk
    email = instance.email
    callback = partial(
        erase_contact_from_datamailer,
        user_id=user_id,
        email=email,
    )
    transaction.on_commit(callback)


@receiver(post_save, sender=Enrollment)
def sync_enrollment_to_datamailer(sender, instance, created, **kwargs):
    if not created:
        return

    callback = partial(sync_enrollment_recipient_list, instance)
    transaction.on_commit(callback)


@receiver(post_delete, sender=CourseRegistration)
def remove_registration_from_datamailer(sender, instance, **kwargs):
    callback = partial(remove_registration_recipient_list, instance)
    transaction.on_commit(callback)


@receiver(post_delete, sender=Enrollment)
def remove_enrollment_from_datamailer(sender, instance, **kwargs):
    callback = partial(remove_enrollment_recipient_list, instance)
    transaction.on_commit(callback)


@receiver(post_delete, sender=Submission)
def remove_homework_submission_from_datamailer(sender, instance, **kwargs):
    callback = partial(remove_homework_submission_recipient_list, instance)
    transaction.on_commit(callback)


@receiver(post_delete, sender=ProjectSubmission)
def remove_project_submission_from_datamailer(sender, instance, **kwargs):
    callback = partial(remove_project_submission_recipient_list, instance)
    transaction.on_commit(callback)
