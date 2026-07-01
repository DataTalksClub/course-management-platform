from collections import OrderedDict

from django.core.management.base import CommandError

from course_management.datamailer.payloads import (
    RecipientListMemberPayload,
    course_graduate_recipient_list_payload,
    enrollment_recipient_list_payload,
    homework_submission_recipient_list_payload,
    project_passed_recipient_list_payload,
    project_submission_recipient_list_payload,
    registration_recipient_list_payload,
)
from courses.models import (
    CourseRegistration,
    Enrollment,
    Project,
    ProjectSubmission,
    Submission,
)


RECIPIENT_LIST_KINDS = [
    "registrations",
    "enrollments",
    "homework",
    "project",
    "project-passed",
    "graduates",
]
PROJECT_FILTER_KINDS = {"project", "project-passed"}


def add_member_to_batches(batches, item):
    payload = item.payload
    batch = batches.setdefault(
        item.list_key,
        {
            "audience": payload["audience"],
            "client": payload["client"],
            "list": payload["list"],
            "members": [],
        },
    )
    member = {
        "source_object_key": item.source_object_key,
        "email": payload["member"]["email"],
        "status": payload["member"]["status"],
        "metadata": payload["member"]["metadata"],
    }
    batch["members"].append(member)


def add_payload_members_to_batches(batches, list_key, payload):
    batch = batches.setdefault(
        list_key,
        {
            "audience": payload["audience"],
            "client": payload["client"],
            "list": payload["list"],
            "members": [],
        },
    )
    batch["members"].extend(payload["members"])


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


def project_queryset(course_slug, project_slug):
    queryset = ProjectSubmission.objects.select_related(
        "project",
        "project__course",
    ).filter(passed=True)
    if course_slug:
        queryset = queryset.filter(project__course__slug=course_slug)
    if project_slug:
        queryset = queryset.filter(project__slug=project_slug)
    project_ids = (
        queryset.order_by("project_id")
        .values_list("project_id", flat=True)
        .distinct()
    )
    return (
        Project.objects.filter(pk__in=project_ids)
        .select_related("course")
        .order_by("pk")
    )


def graduates_queryset(course_slug):
    queryset = (
        Enrollment.objects.select_related("student", "course")
        .exclude(certificate_url__isnull=True)
        .exclude(certificate_url="")
        .order_by("pk")
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


RECIPIENT_LIST_SOURCES = {
    "registrations": (
        lambda c, h, p: registration_queryset(c),
        registration_recipient_list_payload,
    ),
    "enrollments": (
        lambda c, h, p: enrollment_queryset(c),
        enrollment_recipient_list_payload,
    ),
    "homework": (
        lambda c, h, p: homework_submission_queryset(c, h),
        homework_submission_recipient_list_payload,
    ),
    "project": (
        lambda c, h, p: project_submission_queryset(c, p),
        project_submission_recipient_list_payload,
    ),
    "project-passed": (
        lambda c, h, p: project_queryset(c, p),
        project_passed_recipient_list_payload,
    ),
    "graduates": (
        lambda c, h, p: graduates_queryset(c),
        course_graduate_recipient_list_payload,
    ),
}


def build_batches(
    kind, *, course_slug="", homework_slug="", project_slug=""
):
    source = RECIPIENT_LIST_SOURCES.get(kind)
    if source is None:
        raise CommandError(f"Unknown recipient list kind: {kind}")

    queryset_fn, payload_for = source
    batches = OrderedDict()
    objects = queryset_fn(course_slug, homework_slug, project_slug)
    for obj in objects:
        item = payload_for(obj)
        if item is None:
            continue
        if isinstance(item, RecipientListMemberPayload):
            add_member_to_batches(batches, item)
            continue
        list_key, payload = item
        add_payload_members_to_batches(batches, list_key, payload)
    return batches
