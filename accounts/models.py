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
