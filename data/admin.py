
from django.contrib import admin

from data.models import (
    DatamailerContactEvent,
    DatamailerOutboxDispatchRun,
    DatamailerOutboxEvent,
)


@admin.register(DatamailerContactEvent)
class DatamailerContactEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "email",
        "client",
        "audience",
        "created_at",
    )
    list_filter = ("event_type", "client", "audience")
    search_fields = ("event_id", "email")
    readonly_fields = ("created_at",)


@admin.register(DatamailerOutboxEvent)
class DatamailerOutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "status",
        "ordering_key",
        "attempt_count",
        "next_attempt_at",
        "created_at",
    )
    list_filter = ("status", "event_type")
    search_fields = ("event_id", "idempotency_key", "ordering_key")
    readonly_fields = (
        "event_id",
        "event_type",
        "idempotency_key",
        "ordering_key",
        "payload",
        "attempt_count",
        "last_attempt_at",
        "acked_at",
        "last_error",
        "response_payload",
        "occurred_at",
        "created_at",
        "updated_at",
    )


@admin.register(DatamailerOutboxDispatchRun)
class DatamailerOutboxDispatchRunAdmin(admin.ModelAdmin):
    list_display = (
        "started_at",
        "status",
        "processed_count",
        "acked_count",
        "retrying_count",
        "failed_count",
    )
    list_filter = ("status",)
    readonly_fields = (
        "started_at",
        "finished_at",
        "status",
        "processed_count",
        "acked_count",
        "retrying_count",
        "failed_count",
        "last_error",
        "created_at",
    )
