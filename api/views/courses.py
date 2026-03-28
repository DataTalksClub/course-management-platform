from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from accounts.auth import token_required
from courses.models import Course

from api.utils import require_methods


@token_required
@require_methods("GET")
def courses_list_view(request):
    """GET /api/courses/ - List all courses."""
    courses = Course.objects.all().order_by("id")

    courses_data = []
    for course in courses:
        courses_data.append({
            "slug": course.slug,
            "title": course.title,
            "description": course.description,
            "finished": course.finished,
        })

    return JsonResponse({"courses": courses_data})


@token_required
@require_methods("GET")
def course_detail_view(request, course_slug):
    """GET /api/courses/<slug>/ - Course details."""
    course = get_object_or_404(Course, slug=course_slug)

    homeworks = course.homework_set.all().order_by("id")
    projects = course.project_set.all().order_by("id")

    return JsonResponse({
        "slug": course.slug,
        "title": course.title,
        "description": course.description,
        "finished": course.finished,
        "social_media_hashtag": course.social_media_hashtag,
        "faq_document_url": course.faq_document_url,
        "homeworks": [
            {
                "id": hw.id,
                "slug": hw.slug,
                "title": hw.title,
                "due_date": hw.due_date.isoformat(),
                "state": hw.state,
            }
            for hw in homeworks
        ],
        "projects": [
            {
                "id": p.id,
                "slug": p.slug,
                "title": p.title,
                "submission_due_date": p.submission_due_date.isoformat(),
                "peer_review_due_date": p.peer_review_due_date.isoformat(),
                "state": p.state,
            }
            for p in projects
        ],
    })
