import logging
import statistics

from typing import List

from django.http import HttpRequest, HttpResponse

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect

from django.db.models import Prefetch, Value, Count, Q
from django.db.models import Case, When, IntegerField
from django.db.models.functions import Coalesce

from django.contrib.auth.decorators import login_required

from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Submission,
    Enrollment,
    Project,
    ProjectSubmission,
    ProjectState,
    User,
)

from .forms import EnrollmentForm

logger = logging.getLogger(__name__)


def course_list(request):
    courses = Course.objects.filter(visible=True).order_by("-id")

    active_courses = []
    finished_courses = []

    for course in courses:
        if course.finished:
            finished_courses.append(course)
        else:
            active_courses.append(course)

    context = {
        "active_courses": active_courses,
        "finished_courses": finished_courses,
    }

    return render(
        request,
        "courses/course_list.html",
        context,
    )


def get_projects_for_course(
    course: Course, user: User
) -> List[Project]:
    if user.is_authenticated:
        queryset = ProjectSubmission.objects.filter(student=user)
    else:
        queryset = ProjectSubmission.objects.none()

    submissions_prefetch = Prefetch(
        "projectsubmission_set",
        queryset=queryset,
        to_attr="submissions",
    )

    projects = (
        Project.objects.filter(course=course)
        .prefetch_related(submissions_prefetch)
        .order_by("id")
    )

    for project in projects:
        update_project_with_additional_info(project)

    return list(projects)


def update_project_with_additional_info(project: Project) -> None:
    days_until_submission_due = 0

    if project.submission_due_date > timezone.now():
        days_until_submission_due = (
            project.submission_due_date - timezone.now()
        ).days

    project.days_until_submission_due = days_until_submission_due

    days_until_pr_due = 0
    if project.peer_review_due_date > timezone.now():
        days_until_pr_due = (
            project.peer_review_due_date - timezone.now()
        ).days

    project.days_until_pr_due = days_until_pr_due

    project.badge_state_name = "Not submitted"
    project.badge_css_class = "bg-secondary"
    project.submitted = False
    project.score = None

    if project.state == ProjectState.CLOSED.value:
        project.badge_state_name = "Closed"
    elif project.state == ProjectState.COLLECTING_SUBMISSIONS.value:
        project.badge_state_name = "Open"
        project.badge_css_class = "bg-warning"
    elif project.state == ProjectState.PEER_REVIEWING.value:
        pass
    elif project.state == ProjectState.COMPLETED.value:
        pass
    else:
        # log unknown state
        pass

    if not project.submissions:
        return

    submission = project.submissions[0]
    project.submitted = True

    project.submitted_at = submission.submitted_at

    if project.state == ProjectState.COLLECTING_SUBMISSIONS.value:
        project.badge_state_name = "Submitted"
        project.badge_css_class = "bg-info"

    elif project.state == ProjectState.PEER_REVIEWING.value:
        project.badge_state_name = "Review"
        project.badge_css_class = "bg-danger"

    elif project.state == ProjectState.COMPLETED.value:
        project.score = submission.total_score

        if submission.passed:
            project.badge_state_name = f"Passed ({project.score})"
            project.badge_css_class = "bg-success"
        else:
            project.badge_state_name = f"Failed ({project.score})"


def course_view(request: HttpRequest, course_slug: str) -> HttpResponse:
    course = get_object_or_404(Course, slug=course_slug)

    user = request.user
    homeworks = get_homeworks_for_course(course, user)
    projects = get_projects_for_course(course, user)

    has_completed_projects = False
    for project in projects:
        if project.state == ProjectState.COMPLETED.value:
            has_completed_projects = True

    total_score = None
    if user.is_authenticated:
        try:
            enrollment = Enrollment.objects.get(
                student=user,
                course=course,
            )
            total_score = enrollment.total_score
        except Enrollment.DoesNotExist:
            pass

    context = {
        "course": course,
        "homeworks": homeworks,
        "projects": projects,
        "has_completed_projects": has_completed_projects,
        "is_authenticated": user.is_authenticated,
        "total_score": total_score,
    }

    return render(request, "courses/course.html", context)


def get_homeworks_for_course(course: Course, user) -> List[Homework]:
    if user.is_authenticated:
        queryset = Submission.objects.filter(student=user)
    else:
        queryset = Submission.objects.none()

    submissions_prefetch = Prefetch(
        "submission_set", queryset=queryset, to_attr="submissions"
    )

    homeworks = (
        Homework.objects.filter(course=course)
        .prefetch_related(submissions_prefetch)
        .order_by("due_date")
    )

    for hw in homeworks:
        update_homework_with_additional_info(hw)

    return list(homeworks)


def update_homework_with_additional_info(homework: Homework) -> None:
    days_until_due = 0

    if homework.due_date > timezone.now():
        days_until_due = (homework.due_date - timezone.now()).days + 1

    homework.days_until_due = days_until_due
    homework.submitted = False
    homework.score = None

    if not homework.submissions:
        return

    submission = homework.submissions[0]

    homework.submitted = True
    if homework.is_scored():
        homework.score = submission.total_score
    else:
        homework.submitted_at = submission.submitted_at


def leaderboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)

    user = request.user
    current_student_enrollment = None
    current_student_enrollment_id = None

    if user.is_authenticated:
        current_student_enrollment, _ = (
            Enrollment.objects.get_or_create(
                student=user,
                course=course,
            )
        )
        current_student_enrollment_id = current_student_enrollment.id

    enrollments = Enrollment.objects.filter(course=course).order_by(
        Coalesce("position_on_leaderboard", Value(999999)),
        "id",
    )

    context = {
        "enrollments": enrollments,
        "course": course,
        "current_student_enrollment": current_student_enrollment,
        "current_student_enrollment_id": current_student_enrollment_id,
    }

    return render(request, "courses/leaderboard.html", context)


def leaderboard_score_breakdown_view(
    request, course_slug: str, enrollment_id: int
):
    enrollment = get_object_or_404(
        Enrollment, id=enrollment_id, course__slug=course_slug
    )

    state_order = Case(
        When(homework__state=HomeworkState.SCORED.value, then=Value(0)),
        When(homework__state=HomeworkState.OPEN.value, then=Value(1)),
        When(homework__state=HomeworkState.CLOSED.value, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )

    # Update the queryset to use the custom sorting order
    homework_submissions = Submission.objects.filter(
        enrollment=enrollment
    ).order_by(state_order, "homework__id")

    project_submissions = ProjectSubmission.objects.filter(
        enrollment=enrollment
    ).order_by("project__id")

    context = {
        "enrollment": enrollment,
        "submissions": homework_submissions,
        "project_submissions": project_submissions,
    }

    return render(
        request, "courses/leaderboard_score_breakdown.html", context
    )


@login_required
def enrollment_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)

    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    if request.method == "POST":
        form = EnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            form.save()
            return redirect("course", course_slug=course_slug)
        else:
            context = {
                "form": form,
                "course": course,
                "enrollment": enrollment,
            }
            return render(request, "courses/enrollment.html", context)

    form = EnrollmentForm(instance=enrollment)

    context = {
        "form": form,
        "course": course,
        "enrollment": enrollment,
    }

    return render(request, "courses/enrollment.html", context)


def list_all_project_submissions_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)

    submissions = (
        ProjectSubmission.objects.filter(project__course=course)
        .select_related("project", "enrollment")
        .annotate(
            display_score=Case(
                When(
                    project__state=ProjectState.COMPLETED.value,
                    then="project_score",
                ),
                default=Value(-1),
                output_field=IntegerField(),
            )
        )
        .order_by("-display_score", "project__id", "submitted_at")
    )

    context = {
        "course": course,
        "submissions": submissions,
        "is_authenticated": request.user.is_authenticated,
    }

    return render(request, "projects/list_all.html", context)


def dashboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)

    # Get total enrollments
    total_enrollments = Enrollment.objects.filter(course=course).count()

    # Get all project submissions with related data in one query
    project_submissions = (
        ProjectSubmission.objects.filter(project__course=course)
        .select_related("project", "enrollment")
        .values("time_spent", "total_score", "passed")
    )

    # Convert to list once for processing
    project_submissions_list = list(project_submissions)

    # Calculate project completion
    total_projects = Project.objects.filter(course=course).count()
    total_possible_project_submissions = (
        total_enrollments * total_projects
    )
    project_completion_rate = (
        (
            len(project_submissions_list)
            / total_possible_project_submissions
            * 100
        )
        if total_possible_project_submissions > 0
        else 0
    )

    # Process project data efficiently
    project_time_spent = [
        s["time_spent"]
        for s in project_submissions_list
        if s["time_spent"] is not None
    ]
    project_scores = [
        s["total_score"]
        for s in project_submissions_list
        if s["total_score"] is not None
    ]
    project_pass_count = sum(
        1 for s in project_submissions_list if s["passed"]
    )
    project_fail_count = sum(
        1 for s in project_submissions_list if not s["passed"]
    )

    # Calculate average total scores
    enrollments_with_scores = Enrollment.objects.filter(
        course=course, total_score__isnull=False
    ).values_list("total_score", flat=True)
    avg_total_score = (
        statistics.mean(enrollments_with_scores)
        if enrollments_with_scores
        else 0
    )

    # Helper function to calculate quartiles safely
    def safe_quartiles(data):
        if len(data) < 3:
            return None, None, None
        try:
            q25, median, q75 = statistics.quantiles(data, n=4)
            return q25, median, q75
        except:
            return None, None, None

    # Calculate quartiles for project metrics
    project_time_q25, project_time_median, project_time_q75 = (
        safe_quartiles(project_time_spent)
    )
    project_score_q25, project_score_median, project_score_q75 = (
        safe_quartiles(project_scores)
    )

    # Get homework data efficiently - fetch all at once
    homeworks = Homework.objects.filter(course=course).order_by("id")

    # Get all homework submissions in one query
    all_hw_submissions = (
        Submission.objects.filter(homework__course=course)
        .select_related("homework")
        .values(
            "homework_id",
            "time_spent_lectures",
            "time_spent_homework",
            "total_score",
        )
    )

    # Group submissions by homework
    hw_submissions_by_homework = {}
    for submission in all_hw_submissions:
        hw_id = submission["homework_id"]
        if hw_id not in hw_submissions_by_homework:
            hw_submissions_by_homework[hw_id] = []
        hw_submissions_by_homework[hw_id].append(submission)

    homework_stats = []
    for homework in homeworks:
        hw_submissions = hw_submissions_by_homework.get(homework.id, [])

        # Process homework data efficiently
        hw_time_lecture = [
            s["time_spent_lectures"]
            for s in hw_submissions
            if s["time_spent_lectures"] is not None
        ]
        hw_time_homework = [
            s["time_spent_homework"]
            for s in hw_submissions
            if s["time_spent_homework"] is not None
        ]
        hw_scores = [
            s["total_score"]
            for s in hw_submissions
            if s["total_score"] is not None
        ]

        # Calculate total time (lecture + homework) for each submission
        hw_time_total = []
        for s in hw_submissions:
            if (
                s["time_spent_lectures"] is not None
                and s["time_spent_homework"] is not None
            ):
                hw_time_total.append(
                    s["time_spent_lectures"] + s["time_spent_homework"]
                )

        # Calculate quartiles for this homework
        (
            hw_time_lecture_q25,
            hw_time_lecture_median,
            hw_time_lecture_q75,
        ) = safe_quartiles(hw_time_lecture)
        (
            hw_time_homework_q25,
            hw_time_homework_median,
            hw_time_homework_q75,
        ) = safe_quartiles(hw_time_homework)
        hw_time_total_q25, hw_time_total_median, hw_time_total_q75 = (
            safe_quartiles(hw_time_total)
        )
        hw_score_q25, hw_score_median, hw_score_q75 = safe_quartiles(
            hw_scores
        )

        homework_stats.append(
            {
                "homework": homework,
                "submissions_count": len(hw_submissions),
                "time_lecture_q25": hw_time_lecture_q25,
                "time_lecture_median": hw_time_lecture_median,
                "time_lecture_q75": hw_time_lecture_q75,
                "time_lecture_median_formatted": f"{hw_time_lecture_median:.0f}"
                if hw_time_lecture_median
                and hw_time_lecture_median % 1 == 0
                else f"{hw_time_lecture_median:.1f}"
                if hw_time_lecture_median
                else None,
                "time_homework_q25": hw_time_homework_q25,
                "time_homework_median": hw_time_homework_median,
                "time_homework_q75": hw_time_homework_q75,
                "time_homework_median_formatted": f"{hw_time_homework_median:.0f}"
                if hw_time_homework_median
                and hw_time_homework_median % 1 == 0
                else f"{hw_time_homework_median:.1f}"
                if hw_time_homework_median
                else None,
                "time_total_q25": hw_time_total_q25,
                "time_total_median": hw_time_total_median,
                "time_total_q75": hw_time_total_q75,
                "time_total_median_formatted": f"{hw_time_total_median:.0f}"
                if hw_time_total_median
                and hw_time_total_median % 1 == 0
                else f"{hw_time_total_median:.1f}"
                if hw_time_total_median
                else None,
                "score_q25": hw_score_q25,
                "score_median": hw_score_median,
                "score_q75": hw_score_q75,
            }
        )

    # Calculate total project submissions
    project_total_submissions = project_pass_count + project_fail_count

    # Get graduates count (enrollments with certificates)
    graduates_count = Enrollment.objects.filter(
        course=course, certificate_url__isnull=False
    ).exclude(certificate_url="").count()

    context = {
        "course": course,
        "total_enrollments": total_enrollments,
        "project_completion_rate": round(project_completion_rate, 1),
        "project_time_q25": project_time_q25,
        "project_time_median": project_time_median,
        "project_time_q75": project_time_q75,
        "project_score_q25": project_score_q25,
        "project_score_median": project_score_median,
        "project_score_q75": project_score_q75,
        "avg_total_score": round(avg_total_score, 1),
        "project_pass_count": project_pass_count,
        "project_fail_count": project_fail_count,
        "project_total_submissions": project_total_submissions,
        "project_passing_score": course.project_passing_score,
        "graduates_count": graduates_count,
        "homework_stats": homework_stats,
    }

    return render(request, "courses/dashboard.html", context)
