from django.db import models


class DatamailerContactEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=80)
    email = models.EmailField(max_length=320)
    occurred_at = models.DateTimeField(null=True, blank=True)
    audience = models.CharField(max_length=120, blank=True)
    client = models.CharField(max_length=120, blank=True)
    preference_key = models.CharField(max_length=80, blank=True)
    payload = models.JSONField(default=dict, blank=True)
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
