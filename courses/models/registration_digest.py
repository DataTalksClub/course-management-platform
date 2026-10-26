"""Daily registration digest sends (one row per Europe/Berlin date)."""

from django.db import models


class RegistrationDigestSend(models.Model):
    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        SKIPPED_EMPTY = "skipped_empty", "Skipped (no registrations)"

    # Europe/Berlin calendar date this digest covers. Unique so restarts and
    # rolling overlap can never record (or send) the same day twice.
    date = models.DateField(unique=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, db_index=True,
    )
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    total_count = models.PositiveIntegerField(default=0)
    confirmed_count = models.PositiveIntegerField(default=0)
    unconfirmed_count = models.PositiveIntegerField(default=0)
    course_count = models.PositiveIntegerField(default=0)
    recipients = models.JSONField(default=list)
    relay_message_ids = models.JSONField(default=list)
    relay_idempotency_keys = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"registration digest {self.date} ({self.status})"
