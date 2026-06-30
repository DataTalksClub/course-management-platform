import logging
from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Prefetch, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import (
    Course,
    Enrollment,
    HomeworkState,
    ProjectState,
    ProjectSubmission,
    Submission,
)

from .forms import LeaderboardComplaintForm

logger = logging.getLogger(__name__)

LEADERBOARD_PAGE_SIZE = 100


@dataclass(frozen=True)
class CurrentLeaderboardStudent:
    enrollment: Enrollment | None
    enrollment_id: int | None


def _current_student_leaderboard_enrollment(course, user):
    if user.is_authenticated:
        try:
            enrollment = Enrollment.objects.get(
                student=user,
                course=course,
            )
            return CurrentLeaderboardStudent(
                enrollment=enrollment,
                enrollment_id=enrollment.id,
            )
        except Enrollment.DoesNotExist:
            pass

    return CurrentLeaderboardStudent(enrollment=None, enrollment_id=None)


def _completed_project_submissions_prefetch():
    return Prefetch(
        "projectsubmission_set",
        queryset=ProjectSubmission.objects.filter(
            project__state=ProjectState.COMPLETED.value,
            volunteer_review_only=False,
        )
        .select_related("project")
        .order_by("project__id"),
        to_attr="completed_project_submissions",
    )


def _serialize_leaderboard_enrollment(enrollment):
    passed_projects = []
    completed_submissions = enrollment.completed_project_submissions
    for index, submission in enumerate(completed_submissions, 1):
        if not submission.passed:
            continue
        passed_project = {
            "title": submission.project.title,
            "slug": submission.project.slug,
            "attempt": index,
            "medal_index": ((index - 1) % 5) + 1,
        }
        passed_projects.append(passed_project)

    return {
        "id": enrollment.id,
        "display_name": enrollment.display_name,
        "total_score": enrollment.total_score,
        "position_on_leaderboard": enrollment.position_on_leaderboard,
        "passed_projects": passed_projects,
    }


def _build_leaderboard_data(course, cache_key):
    logger.info(f"Cache miss for leaderboard of course {course.slug}")
    enrollments = (
        Enrollment.objects.filter(
            course=course,
            display_on_leaderboard=True,
        )
        .select_related("student")
        .prefetch_related(_completed_project_submissions_prefetch())
        .order_by(
            Coalesce("position_on_leaderboard", Value(999999)),
            "id",
        )
    )
    # Store dictionaries in cache to avoid stale model instances.
    enrollments_data = []
    for enrollment in enrollments:
        enrollment_data = _serialize_leaderboard_enrollment(enrollment)
        enrollments_data.append(enrollment_data)
    cache.set(cache_key, enrollments_data, 3600)
    return enrollments_data


def _leaderboard_cache_missing_current_student(
    enrollments_data,
    current_student: CurrentLeaderboardStudent,
):
    if current_student.enrollment_id is None:
        return False
    if not current_student.enrollment.display_on_leaderboard:
        return False

    for enrollment in enrollments_data:
        if enrollment["id"] == current_student.enrollment_id:
            return False

    return True


def _get_leaderboard_data(
    course,
    current_student: CurrentLeaderboardStudent,
):
    cache_key = f"leaderboard:{course.id}"
    enrollments_data = cache.get(cache_key)

    if enrollments_data is None:
        return _build_leaderboard_data(course, cache_key)

    logger.info(f"Cache hit for leaderboard of course {course.slug}")
    if _leaderboard_cache_missing_current_student(
        enrollments_data,
        current_student,
    ):
        return _build_leaderboard_data(course, cache_key)

    return enrollments_data


def _current_student_page_number(
    enrollments_data,
    current_student: CurrentLeaderboardStudent,
):
    if (
        current_student.enrollment_id is None
        or not current_student.enrollment.display_on_leaderboard
    ):
        return None

    for index, enrollment in enumerate(enrollments_data):
        if enrollment["id"] == current_student.enrollment_id:
            return (index // LEADERBOARD_PAGE_SIZE) + 1

    return None


def leaderboard_context(course, user, page_number):
    current_student = _current_student_leaderboard_enrollment(course, user)
    enrollments_data = _get_leaderboard_data(
        course,
        current_student,
    )

    paginator = Paginator(enrollments_data, LEADERBOARD_PAGE_SIZE)
    page_obj = paginator.get_page(page_number)
    enrollments_page = page_obj.object_list

    current_student_page_number = _current_student_page_number(
        enrollments_data,
        current_student,
    )

    return {
        "enrollments": enrollments_page,
        "page_obj": page_obj,
        "page_range": paginator.get_elided_page_range(page_obj.number),
        "total_enrollments": paginator.count,
        "course": course,
        "current_student_enrollment": current_student.enrollment,
        "current_student_enrollment_id": current_student.enrollment_id,
        "current_student_page_number": current_student_page_number,
    }


def leaderboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    context = leaderboard_context(course, request.user, request.GET.get("page"))

    return render(request, "courses/leaderboard.html", context)


def invalidate_leaderboard_cache(course_id: int) -> None:
    cache.delete(f"leaderboard:{course_id}")
    version_key = f"leaderboard_cache_version:{course_id}"
    cache.set(version_key, cache.get(version_key, 1) + 1, None)


def leaderboard_score_breakdown_view(
    request, course_slug: str, enrollment_id: int
):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "course"),
        id=enrollment_id,
        course__slug=course_slug,
    )
    context = _leaderboard_score_breakdown_context(enrollment, request.user)

    return render(
        request, "courses/leaderboard_score_breakdown.html", context
    )


def _leaderboard_score_breakdown_context(enrollment, user):
    is_own_record = (
        user.is_authenticated and user.id == enrollment.student_id
    )
    public_profile = (
        enrollment.student if enrollment.display_public_profile else None
    )

    return {
        "enrollment": enrollment,
        "public_profile": public_profile,
        "show_public_profile_settings_link": (
            is_own_record and public_profile is None
        ),
        "submissions": _leaderboard_homework_submissions(enrollment),
        "project_submissions": _leaderboard_project_submissions(enrollment),
    }


def _leaderboard_homework_state_order():
    return Case(
        When(homework__state=HomeworkState.SCORED.value, then=Value(0)),
        When(homework__state=HomeworkState.OPEN.value, then=Value(1)),
        When(homework__state=HomeworkState.CLOSED.value, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )


def _leaderboard_homework_submissions(enrollment):
    return Submission.objects.filter(
        enrollment=enrollment
    ).order_by(_leaderboard_homework_state_order(), "homework__id")


def _leaderboard_project_submissions(enrollment):
    return ProjectSubmission.objects.filter(
        enrollment=enrollment,
        volunteer_review_only=False,
    ).order_by("project__id")


def _save_leaderboard_complaint(form, enrollment, reporter):
    complaint = form.save(commit=False)
    complaint.enrollment = enrollment
    complaint.reporter = reporter
    complaint.save()


def _leaderboard_complaint_post_response(
    request,
    form,
    enrollment,
    course_slug,
):
    if not form.is_valid():
        return None

    _save_leaderboard_complaint(form, enrollment, request.user)
    messages.success(
        request,
        "Thanks. The course team will review this leaderboard record.",
    )
    return redirect(
        "leaderboard_score_breakdown",
        course_slug=course_slug,
        enrollment_id=enrollment.id,
    )


@login_required
def leaderboard_complaint_view(
    request, course_slug: str, enrollment_id: int
):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("course", "student"),
        id=enrollment_id,
        course__slug=course_slug,
    )

    if request.method == "POST":
        form = LeaderboardComplaintForm(request.POST)
        response = _leaderboard_complaint_post_response(
            request,
            form,
            enrollment,
            course_slug,
        )
        if response is not None:
            return response
    else:
        form = LeaderboardComplaintForm()

    context = {
        "enrollment": enrollment,
        "course": enrollment.course,
        "form": form,
    }
    return render(request, "courses/leaderboard_complaint.html", context)
