import secrets

from django.db import models
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('instructor', 'Instructor'),
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    certificate_name = models.CharField(
        verbose_name="Certificate name",
        max_length=255,
        blank=True,
        null=True,
        help_text="Your actual name that will appear on your certificates"
    )
    country = models.CharField(
        verbose_name="Country",
        max_length=100,
        blank=True,
    )
    region = models.CharField(
        verbose_name="Region",
        max_length=100,
        blank=True,
    )
    registration_role = models.CharField(
        verbose_name="Registration role",
        max_length=40,
        blank=True,
        help_text="Role last used on a course registration form",
    )
    github_url = models.URLField(
        verbose_name="GitHub URL",
        blank=True,
        null=True,
    )
    linkedin_url = models.URLField(
        verbose_name="LinkedIn URL",
        blank=True,
        null=True,
    )
    personal_website_url = models.URLField(
        verbose_name="Personal website URL",
        blank=True,
        null=True,
    )
    about_me = models.TextField(
        verbose_name="About me",
        blank=True,
        null=True,
    )
    dark_mode = models.BooleanField(
        verbose_name="Dark mode",
        default=False,
        help_text="Enable dark mode theme"
    )
    email_submission_confirmations = models.BooleanField(
        verbose_name="Submission confirmations",
        default=True,
        help_text=(
            "Receive homework and project submission emails with a copy "
            "of submitted results."
        ),
    )
    email_deadline_reminders = models.BooleanField(
        verbose_name="Deadline reminders",
        default=True,
        help_text=(
            "Receive reminder emails when homework or peer review "
            "deadlines are within 24 hours and you have not submitted, "
            "plus project reminders one week before and one day before "
            "the deadline when you have not submitted. Peer review "
            "reminders are sent when assigned reviews are unfinished."
        ),
    )

    def __str__(self):
        # safest is to display something stable
        return self.username or self.email or str(self.pk)


class Token(models.Model):
    key = models.CharField(max_length=40, primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_urlsafe(16)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.key
