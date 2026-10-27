from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from courses.models.course import (
    Course,
    Enrollment,
    LeaderboardComplaint,
    RegistrationCampaign,
)
from courses.models.homework import (
    Homework,
    HomeworkState,
)
from courses.models.project import (
    Project,
    ProjectState,
)
from cadmin.deadline_extension import (
    EXTENSION_OPTIONS,
    project_extension_plan,
)
from course_management.datamailer.score_notification_status import (
    get_homework_score_notification_status,
    get_project_score_notification_status,
)
from .campaign_metrics import registration_campaign_metrics
from .helpers import staff_required
from courses.scoring_queue import (
    attach_homework_scoring_status,
    attach_project_scoring_status,
)


@staff_required
def course_list(request):
    """List all courses with admin actions"""
    courses = Course.objects.all().order_by("finished", "-id")

    context = {
        "courses": courses,
    }

    response = render(request, "cadmin/course_list.html", context)
    return response


def course_homeworks_for_admin(course):
    homework_queryset = (
        Homework.objects.filter(course=course)
        .annotate(submissions_count=Count("submission"))
        .order_by("due_date")
    )
    homeworks = list(homework_queryset)
    for homework in homeworks:
        homework.can_score = homework.state in [
            HomeworkState.OPEN.value,
            HomeworkState.CLOSED.value,
        ]
        homework.can_notify_scores = (
            homework.state == HomeworkState.SCORED.value
        )
        homework.can_extend_deadline = (
            homework.state == HomeworkState.OPEN.value
        )
        homework.score_notification_status = (
            get_homework_score_notification_status(homework)
        )
    attach_homework_scoring_status(homeworks)
    return homeworks


def course_projects_for_admin(course):
    project_queryset = (
        Project.objects.filter(course=course)
        .annotate(submissions_count=Count("projectsubmission"))
        .order_by("id")
    )
    projects = list(project_queryset)
    for project in projects:
        project.needs_review_assignment = (
            project.state == ProjectState.COLLECTING_SUBMISSIONS.value
        )
        project.needs_scoring = (
            project.state == ProjectState.PEER_REVIEWING.value
        )
        project.can_notify_peer_reviews = (
            project.state == ProjectState.PEER_REVIEWING.value
        )
        project.can_notify_scores = (
            project.state == ProjectState.COMPLETED.value
        )
        project.score_notification_status = (
            get_project_score_notification_status(project)
        )
        extension_fields, extension_label = project_extension_plan(
            project
        )
        project.can_extend_deadline = extension_fields is not None
        project.extend_deadline_label = extension_label
    attach_project_scoring_status(projects)
    return projects


def course_support_metrics(course):
    enrollments = Enrollment.objects.filter(course=course)
    disabled_lip = enrollments.filter(
        disable_learning_in_public=True
    ).count()
    zero_score = enrollments.filter(total_score=0).count()
    hidden_leaderboard = enrollments.filter(
        display_on_leaderboard=False
    ).count()
    open_complaints = LeaderboardComplaint.objects.filter(
        enrollment__course=course,
        resolved=False,
    ).count()
    return {
        "disabled_lip": disabled_lip,
        "zero_score": zero_score,
        "hidden_leaderboard": hidden_leaderboard,
        "open_complaints": open_complaints,
    }


def course_registration_metrics(course):
    campaigns = (
        RegistrationCampaign.objects.filter(current_course=course)
        .select_related("current_course")
        .order_by("title", "slug")
    )
    registration_metrics = []
    primary_campaign = None
    for campaign in campaigns:
        if primary_campaign is None:
            primary_campaign = campaign
        metric = registration_campaign_metrics(campaign)
        registration_metrics.append(metric)

    return {
        "registration_metrics": registration_metrics,
        "primary_campaign": primary_campaign,
    }


def course_admin_context(course):
    context = course_registration_metrics(course)
    homeworks = course_homeworks_for_admin(course)
    projects = course_projects_for_admin(course)
    total_enrollments = course.enrollment_set.count()
    support_metrics = course_support_metrics(course)
    failing_assignments = [
        item.title
        for item in homeworks + projects
        if getattr(item, "score_notification_status", None)
        and item.score_notification_status.is_failed_or_retrying
    ]
    course_score_notification_warning = ""
    if failing_assignments:
        assignments_str = ", ".join(failing_assignments)
        course_score_notification_warning = (
            f"Score notifications for {assignments_str} could not be delivered: "
            "Relay is unavailable or rejected the send. Delivery is retrying automatically."
        )

    context.update(
        {
            "course": course,
            "homeworks": homeworks,
            "projects": projects,
            "total_enrollments": total_enrollments,
            "support_metrics": support_metrics,
            "extension_options": EXTENSION_OPTIONS,
            "course_score_notification_warning": course_score_notification_warning,
        }
    )
    return context


@staff_required
def course_admin(request, course_slug):
    """Admin panel for a specific course"""
    course = get_object_or_404(Course, slug=course_slug)
    context = course_admin_context(course)
    response = render(
        request,
        "cadmin/course_admin.html",
        context,
    )
    return response
