import secrets
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


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


class Token(models.Model):
    key = models.CharField(max_length=40, primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_urlsafe(16)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.key


class EmailVerificationCode(models.Model):
    email = models.EmailField()
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    
    class Meta:
        indexes = [
            models.Index(fields=['email', 'code']),
            models.Index(fields=['created_at']),
        ]
    
    @classmethod
    def generate_code(cls):
        return f"{secrets.randbelow(1000000):06d}"
    
    @classmethod
    def create_for_email(cls, email):
        # Delete old unused codes for this email
        cls.objects.filter(email=email, used=False).delete()
        
        # Create new code
        code = cls.generate_code()
        return cls.objects.create(email=email, code=code)
    
    def is_valid(self):
        # Code expires after 10 minutes
        expiry_time = self.created_at + timedelta(minutes=10)
        return not self.used and timezone.now() < expiry_time
    
    def __str__(self):
        return f"{self.email} - {self.code}"