from collections import OrderedDict
from dataclasses import dataclass

from django.core.management.base import CommandError

from course_management.datamailer.payloads.base import (
    RecipientListMemberPayload,
    enrollment_recipient_list_payload,
)
from course_management.datamailer.payloads.course_graduates import (
    course_graduate_recipient_list_payload,
)
from course_management.datamailer.payloads.project_outcomes import (
    project_passed_recipient_list_payload,
)
from course_management.datamailer.payloads.registration_members import (
    registration_recipient_list_payload,
)
from course_management.datamailer.payloads.submissions import (
    homework_submission_recipient_list_payload,
    project_submission_recipient_list_payload,
)
from courses.models.course import (
    CourseRegistration,
    Enrollment,
)
from courses.models.homework import Submission
from courses.models.project import (
    Project,
    ProjectSubmission,
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


@dataclass(frozen=True)
class RecipientListFilters:
    course_slug: str = ""
    homework_slug: str = ""
    project_slug: str = ""


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


def registration_queryset(filters):
    queryset = CourseRegistration.objects.select_related(
        "campaign", "course", "user"
    ).order_by("pk")
    course_slug = filters.course_slug
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


def enrollment_queryset(filters):
    queryset = Enrollment.objects.select_related(
        "student",
        "course",
    ).order_by("pk")
    course_slug = filters.course_slug
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


def homework_submission_queryset(filters):
    queryset = Submission.objects.select_related(
        "student",
        "homework",
        "homework__course",
    ).order_by("pk")
    course_slug = filters.course_slug
    homework_slug = filters.homework_slug
    if course_slug:
        queryset = queryset.filter(homework__course__slug=course_slug)
    if homework_slug:
        queryset = queryset.filter(homework__slug=homework_slug)
    return queryset


def project_submission_queryset(filters):
    queryset = ProjectSubmission.objects.select_related(
        "student",
        "project",
        "project__course",
    ).order_by("pk")
    course_slug = filters.course_slug
    project_slug = filters.project_slug
    if course_slug:
        queryset = queryset.filter(project__course__slug=course_slug)
    if project_slug:
        queryset = queryset.filter(project__slug=project_slug)
    return queryset


def project_queryset(filters):
    queryset = ProjectSubmission.objects.select_related(
        "project",
        "project__course",
    ).filter(passed=True)
    course_slug = filters.course_slug
    project_slug = filters.project_slug
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


def graduates_queryset(filters):
    queryset = (
        Enrollment.objects.select_related("student", "course")
        .exclude(certificate_url__isnull=True)
        .exclude(certificate_url="")
        .order_by("pk")
    )
    course_slug = filters.course_slug
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


RECIPIENT_LIST_SOURCES = {
    "registrations": (
        registration_queryset,
        registration_recipient_list_payload,
    ),
    "enrollments": (
        enrollment_queryset,
        enrollment_recipient_list_payload,
    ),
    "homework": (
        homework_submission_queryset,
        homework_submission_recipient_list_payload,
    ),
    "project": (
        project_submission_queryset,
        project_submission_recipient_list_payload,
    ),
    "project-passed": (
        project_queryset,
        project_passed_recipient_list_payload,
    ),
    "graduates": (
        graduates_queryset,
        course_graduate_recipient_list_payload,
    ),
}


def build_batches(
    kind, *, course_slug="", homework_slug="", project_slug=""
):
    source = RECIPIENT_LIST_SOURCES.get(kind)
    if source is None:
        raise CommandError(f"Unknown recipient list kind: {kind}")

    queryset_for, payload_for = source
    batches = OrderedDict()
    filters = RecipientListFilters(
        course_slug=course_slug,
        homework_slug=homework_slug,
        project_slug=project_slug,
    )
    objects = queryset_for(filters)
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
