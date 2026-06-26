from django.db import models
from django.utils import timezone


class DatamailerContactEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=80)
    email = models.EmailField(max_length=320)
    occurred_at = models.DateTimeField(null=True, blank=True)
    audience = models.CharField(max_length=120, blank=True)
    client = models.CharField(max_length=120, blank=True)
    preference_key = models.CharField(max_length=80, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    duplicate_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["email"], name="dm_events_email_idx"),
            models.Index(
                fields=["event_type", "created_at"],
                name="dm_events_type_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} for {self.email}"


class DatamailerOutboxStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    ACKED = "acked", "Acked"
    RETRYING = "retrying", "Retrying"
    FAILED = "failed", "Failed"
    DEAD = "dead", "Dead"


class DatamailerOutboxEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=80, db_index=True)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    ordering_key = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=DatamailerOutboxStatus.choices,
        default=DatamailerOutboxStatus.PENDING,
        db_index=True,
    )
    payload = models.JSONField(default=dict, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=8)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    acked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                name="dm_outbox_status_next_idx",
            ),
            models.Index(
                fields=["ordering_key", "created_at"],
                name="dm_outbox_ordering_idx",
            ),
            models.Index(
                fields=["event_type", "created_at"],
                name="dm_outbox_type_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} {self.event_id} ({self.status})"


class DatamailerOutboxDispatchRunStatus(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class DatamailerOutboxDispatchRun(models.Model):
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=DatamailerOutboxDispatchRunStatus.choices,
        db_index=True,
    )
    processed_count = models.PositiveIntegerField(default=0)
    acked_count = models.PositiveIntegerField(default=0)
    retrying_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(
                fields=["status", "started_at"],
                name="dm_outbox_run_status_idx",
            ),
        ]

    def __str__(self):
        return f"Datamailer outbox run {self.started_at} ({self.status})"
