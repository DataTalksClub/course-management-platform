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
    Submission,
)
from courses.models.project import (
    Project,
    ProjectState,
    ProjectSubmission,
)
from .campaign_metrics import registration_campaign_metrics
from .helpers import staff_required


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
    homework_queryset = Homework.objects.filter(course=course).order_by(
        "due_date"
    )
    homeworks = list(homework_queryset)
    for homework in homeworks:
        homework.submissions_count = Submission.objects.filter(
            homework=homework
        ).count()
        homework.can_score = homework.state in [
            HomeworkState.OPEN.value,
            HomeworkState.CLOSED.value,
        ]
    return homeworks


def course_projects_for_admin(course):
    project_queryset = Project.objects.filter(course=course).order_by("id")
    projects = list(project_queryset)
    for project in projects:
        project.submissions_count = ProjectSubmission.objects.filter(
            project=project
        ).count()
        project.needs_review_assignment = (
            project.state == ProjectState.COLLECTING_SUBMISSIONS.value
        )
        project.needs_scoring = (
            project.state == ProjectState.PEER_REVIEWING.value
        )
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
    context.update(
        {
            "course": course,
            "homeworks": homeworks,
            "projects": projects,
            "total_enrollments": total_enrollments,
            "support_metrics": support_metrics,
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
