"""Nightly bulk-approval runs for the Production AI Agents campaign (one row per Europe/Berlin date)."""

from django.db import models


class GenmediaApprovalRun(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        STOPPED_AT_LIMIT = "stopped_at_limit", "Stopped at limit"

    # Europe/Berlin calendar date this run covers. Unique so the minutely
    # outbox piggyback (and rolling overlap) can never run the same evening
    # twice: exactly one bulk approval per day, in both DST seasons.
    date = models.DateField(unique=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, db_index=True,
    )
    approved_count = models.PositiveIntegerField(default=0)
    excluded_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"genmedia approval {self.date} ({self.status})"
