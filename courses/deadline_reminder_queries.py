from datetime import datetime, time, timedelta, timezone as datetime_timezone

from django.db.models import Q

from courses.deadline_reminder_types import ReminderWindow
from courses.models.course import Enrollment
from courses.models.homework import (
    Homework,
    HomeworkState,
    Submission,
)
from courses.models.project import (
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
)


def utc_day_window(now, *, days_ahead):
    now_utc = now.astimezone(datetime_timezone.utc)
    target_date = (now_utc + timedelta(days=days_ahead)).date()
    start = datetime.combine(
        target_date,
        time.min,
        tzinfo=datetime_timezone.utc,
    )
    return start, start + timedelta(days=1)


def reminder_window(now, reminder_key):
    days_by_key = {
        "24h": 1,
        "7d": 8,
    }
    return utc_day_window(now, days_ahead=days_by_key[reminder_key])


def matching_reminder_key(deadline, windows):
    for window in windows:
        if is_within_window(deadline, window.start, window.end):
            return window.key
    return None


def is_within_window(value, start, end):
    value_utc = value.astimezone(datetime_timezone.utc)
    return start <= value_utc < end


def homework_reminder_queryset(now, course_slug):
    reminder_start, reminder_end = reminder_window(now, "24h")
    queryset = Homework.objects.select_related("course").filter(
        state=HomeworkState.OPEN.value,
        due_date__gte=reminder_start,
        due_date__lt=reminder_end,
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset.order_by("due_date", "pk")


def project_submission_reminder_windows(now):
    daily_start, daily_end = reminder_window(now, "24h")
    weekly_start, weekly_end = reminder_window(now, "7d")
    return (
        ReminderWindow("24h", daily_start, daily_end),
        ReminderWindow("7d", weekly_start, weekly_end),
    )


def project_submission_reminder_queryset(windows, course_slug):
    daily_window = windows[0]
    weekly_window = windows[1]
    queryset = Project.objects.select_related("course").filter(
        state=ProjectState.COLLECTING_SUBMISSIONS.value,
    ).filter(
        Q(
            submission_due_date__gte=daily_window.start,
            submission_due_date__lt=daily_window.end,
        )
        | Q(
            submission_due_date__gte=weekly_window.start,
            submission_due_date__lt=weekly_window.end,
        )
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset.order_by("submission_due_date", "pk")


def peer_review_reminder_queryset(now, course_slug):
    reminder_start, reminder_end = reminder_window(now, "24h")
    queryset = Project.objects.select_related("course").filter(
        state=ProjectState.PEER_REVIEWING.value,
        peer_review_due_date__gte=reminder_start,
        peer_review_due_date__lt=reminder_end,
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset.order_by("peer_review_due_date", "pk")


def pending_homework_enrollments(homework):
    submitted_student_ids = Submission.objects.filter(
        homework=homework
    ).values("student_id")
    return (
        Enrollment.objects.filter(course=homework.course)
        .exclude(student_id__in=submitted_student_ids)
        .select_related("student", "course")
        .order_by("pk")
    )


def pending_project_submission_enrollments(project):
    submitted_student_ids = ProjectSubmission.objects.filter(
        project=project,
        volunteer_review_only=False,
    ).values("student_id")
    return (
        Enrollment.objects.filter(course=project.course)
        .exclude(student_id__in=submitted_student_ids)
        .select_related("student", "course")
        .order_by("pk")
    )


def pending_peer_review_submissions(project):
    return (
        ProjectSubmission.objects.filter(
            project=project,
            volunteer_review_only=False,
            reviewers__state=PeerReviewState.TO_REVIEW.value,
            reviewers__optional=False,
        )
        .filter(Q(student__email__isnull=False) & ~Q(student__email=""))
        .select_related("student", "enrollment", "project")
        .distinct()
        .order_by("pk")
    )
