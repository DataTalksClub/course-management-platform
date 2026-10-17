from datetime import UTC

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def parse_start_time(value):
    if value is None:
        return None
    error = {
        "starts_at": "Use an offset-aware ISO8601 timestamp or null."
    }
    if not isinstance(value, str):
        raise ValidationError(error)
    try:
        parsed = parse_datetime(value)
    except ValueError:
        parsed = None
    if parsed is None or timezone.is_naive(parsed):
        raise ValidationError(error)
    try:
        return parsed.astimezone(UTC)
    except OverflowError:
        raise ValidationError(error) from None


def validate_start_time(instance):
    start = instance.starts_at
    if start is None:
        return
    if timezone.is_naive(start):
        raise ValidationError(
            {"starts_at": "Start time must include a timezone."}
        )
    for field in (
        "due_date",
        "submission_due_date",
        "peer_review_due_date",
    ):
        end = getattr(instance, field, None)
        if end is not None and start > end:
            raise ValidationError(
                {"starts_at": f"Start time cannot be after {field}."}
            )
    end_date = getattr(instance, "end_date", None)
    if end_date and start.astimezone(UTC).date() > end_date:
        raise ValidationError(
            {
                "starts_at": "Start time cannot be after the course end date (UTC)."
            }
        )


class StartTimeModel(models.Model):
    starts_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        validate_start_time(self)
