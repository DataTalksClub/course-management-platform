from django.db import models
from django.utils import timezone


class ScoringJobKind(models.TextChoices):
    HOMEWORK_SCORE = "homework_score", "Homework score"
    PROJECT_SCORE = "project_score", "Project score"
    PROJECT_ASSIGN_REVIEWS = "project_assign_reviews", "Project assign reviews"


class ScoringJobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class ScoringJob(models.Model):
    kind = models.CharField(max_length=32, choices=ScoringJobKind.choices, db_index=True)
    homework = models.ForeignKey(
        "courses.Homework", null=True, blank=True, on_delete=models.CASCADE
    )
    project = models.ForeignKey(
        "courses.Project", null=True, blank=True, on_delete=models.CASCADE
    )
    force = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16,
        choices=ScoringJobStatus.choices,
        default=ScoringJobStatus.QUEUED,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    requested_by = models.CharField(max_length=255, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    result_message = models.TextField(blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="scoring_job_status_created_idx"),
            models.Index(fields=["kind", "status"], name="scoring_job_kind_status_idx"),
        ]

    def __str__(self):
        target = self.homework_id or self.project_id
        return f"{self.kind} {target} ({self.status})"

    @property
    def is_terminal(self):
        return self.status in {ScoringJobStatus.SUCCEEDED, ScoringJobStatus.FAILED}

    @property
    def is_active(self):
        return self.status in {ScoringJobStatus.QUEUED, ScoringJobStatus.PROCESSING}
