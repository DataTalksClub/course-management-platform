"""Deliberately re-arm the send-once peer-review-assignment notification.

The staff API POST .../notify-peer-reviews/ refuses to send again while a
succeeded (or in-flight) send audit exists. This marks it failed so exactly
one more send is allowed.

    uv run python manage.py reset_peer_review_notification_marker \
        <course_slug> <project_slug> --confirm --reason "..."
"""

from django.core.management.base import BaseCommand, CommandError
from django.shortcuts import get_object_or_404

from course_management.datamailer.sync.peer_review_send_once import (
    peer_review_assignment_idempotency_key,
    reset_peer_review_assignment_send_marker,
)
from courses.models.project import Project


class Command(BaseCommand):
    help = "Reset the send-once marker for a project's peer-review email."

    def add_arguments(self, parser):
        parser.add_argument("course_slug")
        parser.add_argument("project_slug")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required: allow one more peer-review-assignment send.",
        )
        parser.add_argument("--reason", default="manual reset")

    def handle(self, *args, **options):
        project = get_object_or_404(
            Project.objects.select_related("course"),
            course__slug=options["course_slug"],
            slug=options["project_slug"],
        )
        key = peer_review_assignment_idempotency_key(project)
        if not options["confirm"]:
            raise CommandError(
                f"Refusing to reset {key} without --confirm; "
                "a reset allows the email to be sent again."
            )
        count = reset_peer_review_assignment_send_marker(
            project, options["reason"]
        )
        self.stdout.write(f"Reset {count} send-once marker(s) for {key}.")
