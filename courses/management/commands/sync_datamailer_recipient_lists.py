from collections import OrderedDict

import requests
from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer import (
    DatamailerClient,
    DatamailerConfig,
    enrollment_recipient_list_payload,
    homework_submission_recipient_list_payload,
    project_submission_recipient_list_payload,
    registration_recipient_list_payload,
)
from courses.models import (
    CourseRegistration,
    Enrollment,
    ProjectSubmission,
    Submission,
)


def add_member_to_batches(
    batches, list_key, source_object_key, payload
):
    batch = batches.setdefault(
        list_key,
        {
            "audience": payload["audience"],
            "client": payload["client"],
            "list": payload["list"],
            "members": [],
        },
    )
    batch["members"].append(
        {
            "source_object_key": source_object_key,
            "email": payload["member"]["email"],
            "status": payload["member"]["status"],
            "metadata": payload["member"]["metadata"],
        }
    )


def registration_queryset(course_slug):
    queryset = CourseRegistration.objects.select_related(
        "campaign", "course", "user"
    ).order_by("pk")
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


def enrollment_queryset(course_slug):
    queryset = Enrollment.objects.select_related(
        "student",
        "course",
    ).order_by("pk")
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


def homework_submission_queryset(course_slug, homework_slug):
    queryset = Submission.objects.select_related(
        "student",
        "homework",
        "homework__course",
    ).order_by("pk")
    if course_slug:
        queryset = queryset.filter(homework__course__slug=course_slug)
    if homework_slug:
        queryset = queryset.filter(homework__slug=homework_slug)
    return queryset


def project_submission_queryset(course_slug, project_slug):
    queryset = ProjectSubmission.objects.select_related(
        "student",
        "project",
        "project__course",
    ).order_by("pk")
    if course_slug:
        queryset = queryset.filter(project__course__slug=course_slug)
    if project_slug:
        queryset = queryset.filter(project__slug=project_slug)
    return queryset


def build_batches(
    kind, *, course_slug="", homework_slug="", project_slug=""
):
    batches = OrderedDict()

    if kind == "registrations":
        for registration in registration_queryset(course_slug):
            item = registration_recipient_list_payload(registration)
            if item is None:
                continue
            list_key, source_object_key, payload = item
            add_member_to_batches(
                batches, list_key, source_object_key, payload
            )
        return batches

    if kind == "enrollments":
        for enrollment in enrollment_queryset(course_slug):
            item = enrollment_recipient_list_payload(enrollment)
            if item is None:
                continue
            list_key, source_object_key, payload = item
            add_member_to_batches(
                batches, list_key, source_object_key, payload
            )
        return batches

    if kind == "homework":
        for submission in homework_submission_queryset(
            course_slug, homework_slug
        ):
            item = homework_submission_recipient_list_payload(
                submission
            )
            if item is None:
                continue
            list_key, source_object_key, payload = item
            add_member_to_batches(
                batches, list_key, source_object_key, payload
            )
        return batches

    if kind == "project":
        for submission in project_submission_queryset(
            course_slug, project_slug
        ):
            item = project_submission_recipient_list_payload(submission)
            if item is None:
                continue
            list_key, source_object_key, payload = item
            add_member_to_batches(
                batches, list_key, source_object_key, payload
            )
        return batches

    raise CommandError(f"Unknown recipient list kind: {kind}")


class Command(BaseCommand):
    help = "Backfill Datamailer recipient lists from CMP registrations, enrollments, and submissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "kind",
            choices=[
                "registrations",
                "enrollments",
                "homework",
                "project",
            ],
            help="CMP source to sync into Datamailer recipient lists.",
        )
        parser.add_argument(
            "--course-slug",
            default="",
            help="Limit the sync to one course cohort slug.",
        )
        parser.add_argument(
            "--homework-slug",
            default="",
            help="Limit homework sync to one homework slug.",
        )
        parser.add_argument(
            "--project-slug",
            default="",
            help="Limit project sync to one project slug.",
        )
        parser.add_argument(
            "--reconcile",
            action="store_true",
            help="Mark existing Datamailer members absent from CMP as removed.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned batches without calling Datamailer.",
        )

    def handle(self, *args, **options):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )

        kind = options["kind"]
        if kind != "homework" and options["homework_slug"]:
            raise CommandError(
                "--homework-slug can only be used with kind=homework."
            )
        if kind != "project" and options["project_slug"]:
            raise CommandError(
                "--project-slug can only be used with kind=project."
            )

        batches = build_batches(
            kind,
            course_slug=options["course_slug"],
            homework_slug=options["homework_slug"],
            project_slug=options["project_slug"],
        )
        if not batches:
            self.stdout.write(
                "No Datamailer recipient-list members to sync."
            )
            return

        total_members = sum(
            len(payload["members"]) for payload in batches.values()
        )
        self.stdout.write(
            f"Prepared {len(batches)} recipient list(s), {total_members} member(s)."
        )

        if options["dry_run"]:
            for list_key, payload in batches.items():
                self.stdout.write(
                    f"{list_key}: {len(payload['members'])} member(s)"
                )
            return

        client = DatamailerClient(config)
        for list_key, payload in batches.items():
            try:
                if options["reconcile"]:
                    response = client.reconcile_recipient_list_members(
                        list_key, payload
                    )
                else:
                    response = (
                        client.bulk_upsert_recipient_list_members(
                            list_key, payload
                        )
                    )
            except requests.RequestException as exc:
                if config.strict:
                    raise
                raise CommandError(
                    f"Datamailer sync failed for {list_key}: {exc}"
                ) from exc

            active_count = None
            if response:
                active_count = response.get("recipient_list", {}).get(
                    "active_member_count"
                )
            suffix = (
                f"; active={active_count}"
                if active_count is not None
                else ""
            )
            self.stdout.write(
                f"Synced {list_key}: {len(payload['members'])} member(s){suffix}"
            )
