"""Durable, independently retryable Relay application notifications."""

import uuid

from django.db import models
from django.utils import timezone


class ApplicationNotification(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Accepted by Relay"
        FAILED = "failed", "Failed"

    registration = models.ForeignKey(
        "courses.CourseRegistration", on_delete=models.CASCADE,
        related_name="application_notifications",
    )
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)
    decision_sequence = models.PositiveIntegerField(default=0)
    template_key = models.CharField(max_length=80)
    recipient = models.EmailField()
    context = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.PENDING, db_index=True,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_attempt_at = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=100, blank=True)
    relay_message_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["registration", "decision_sequence", "recipient"],
            name="unique_application_notification_recipient",
        )]
