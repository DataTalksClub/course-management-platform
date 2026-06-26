
from django.contrib import admin
from django.contrib import messages
from django.utils import timezone

from data.models import (
    DatamailerContactEvent,
    DatamailerOutboxDispatchRun,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
)


@admin.register(DatamailerContactEvent)
class DatamailerContactEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "email",
        "client",
        "audience",
        "duplicate_count",
        "last_seen_at",
        "created_at",
    )
    list_filter = ("event_type", "client", "audience")
    search_fields = ("event_id", "email")
    readonly_fields = ("created_at", "duplicate_count", "last_seen_at")


@admin.register(DatamailerOutboxEvent)
class DatamailerOutboxEventAdmin(admin.ModelAdmin):
    actions = ("requeue_selected_events",)
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

    @admin.action(description="Requeue failed/dead Datamailer events")
    def requeue_selected_events(self, request, queryset):
        now = timezone.now()
        requeued = queryset.filter(
            status__in=[
                DatamailerOutboxStatus.FAILED,
                DatamailerOutboxStatus.DEAD,
            ]
        ).update(
            status=DatamailerOutboxStatus.RETRYING,
            next_attempt_at=now,
            last_error="",
            updated_at=now,
        )
        self.message_user(
            request,
            f"Requeued {requeued} Datamailer outbox event(s).",
            messages.SUCCESS,
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


@admin.register(DatamailerSendAudit)
class DatamailerSendAuditAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "send_type",
        "status",
        "template_key",
        "category_tag",
        "list_key",
        "intended_count",
        "enqueued_count",
        "skipped_count",
        "idempotent_replay_count",
    )
    list_filter = ("status", "send_type", "category_tag", "event")
    search_fields = ("idempotency_key", "list_key", "template_key", "error")
    readonly_fields = (
        "send_type",
        "status",
        "idempotency_key",
        "template_key",
        "category_tag",
        "list_key",
        "source",
        "event",
        "intended_count",
        "created_count",
        "enqueued_count",
        "skipped_count",
        "idempotent_replay_count",
        "error",
        "response_payload",
        "occurred_at",
        "created_at",
        "updated_at",
    )
