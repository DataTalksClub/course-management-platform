"""Small read-only capability for the Slack bot, separate from staff API tokens."""

import re
import secrets

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from courses.models import Course, Homework, Project
from courses.models.homework import HomeworkState
from courses.models.project import PeerReview, PeerReviewState, ProjectState


SLACK_ID = re.compile(r"[A-Z][A-Z0-9]{2,63}\Z")


def source_url(request, name, **kwargs):
    return request.build_absolute_uri(reverse(name, kwargs=kwargs))


def student_state(request, projects):
    team = request.GET.get("slack_team_id", "")
    user = request.GET.get("slack_user_id", "")
    if not team and not user:
        return {"mapped": False, "projects": []}
    if not SLACK_ID.fullmatch(team) or not SLACK_ID.fullmatch(user):
        return None
    # allauth's Slack provider uses TEAM_USER, never email/name matching.
    account = SocialAccount.objects.filter(
        provider="slack", uid=f"{team}_{user}", user__is_active=True
    ).first()
    if account is None:
        return {"mapped": False, "projects": []}
    counts = []
    for project in projects:
        reviews = PeerReview.objects.filter(
            reviewer__project=project,
            reviewer__student_id=account.user_id,
            reviewer__enrollment__course=project.course,
        )
        counts.append({
            "slug": project.slug,
            "assigned_count": reviews.count(),
            "pending_count": reviews.filter(
                state=PeerReviewState.TO_REVIEW.value
            ).count(),
        })
    return {"mapped": True, "projects": counts}


def homework_state(request, homework):
    return {
        "slug": homework.slug,
        "title": homework.title,
        "state": HomeworkState(homework.state).name,
        "starts_at": homework.starts_at,
        "due_date": homework.due_date,
        "source_url": source_url(
            request, "homework", course_slug=homework.course.slug,
            homework_slug=homework.slug,
        ),
    }


def project_state(request, project):
    return {
        "slug": project.slug,
        "title": project.title,
        "state": ProjectState(project.state).name,
        "starts_at": project.starts_at,
        "submission_due_date": project.submission_due_date,
        "peer_review_due_date": project.peer_review_due_date,
        "peer_review_open": project.state == ProjectState.PEER_REVIEWING.value,
        # The platform has no scheduled peer-review opening timestamp.
        "peer_review_opens_at": None,
        "assignments_created": PeerReview.objects.filter(
            reviewer__project=project
        ).exists(),
        "source_url": source_url(
            request, "project", course_slug=project.course.slug,
            project_slug=project.slug,
        ),
    }


@never_cache
@csrf_exempt
@require_GET
def bot_course_state_view(request, course_slug):
    expected = settings.CMP_BOT_READ_TOKEN
    supplied = request.headers.get("Authorization", "")
    if not expected or not secrets.compare_digest(
        supplied.encode(), f"Bearer {expected}".encode()
    ):
        return JsonResponse({"error": "unauthorized"}, status=401)

    course = get_object_or_404(Course, slug=course_slug, visible=True)
    projects = list(Project.objects.filter(course=course).order_by("id"))
    student = student_state(request, projects)
    if student is None:
        return JsonResponse({"error": "invalid_slack_identity"}, status=400)
    return JsonResponse({
        "schema_version": 1,
        "fetched_at": timezone.now(),
        "course": {
            "slug": course.slug,
            "title": course.title,
            "source_url": source_url(request, "course", course_slug=course.slug),
            "starts_at": course.starts_at,
            "start_date": course.start_date,
            "end_date": course.end_date,
            "finished": course.finished,
        },
        "homeworks": [
            homework_state(request, item)
            for item in Homework.objects.filter(course=course).order_by("id")
        ],
        "projects": [project_state(request, item) for item in projects],
        "student": student,
    })
