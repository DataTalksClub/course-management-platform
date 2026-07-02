from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from courses.models.course import Course, Enrollment

from .course_leaderboard_data import invalidate_leaderboard_cache
from .forms import EnrollmentForm

ENROLLMENT_TOGGLE_FIELDS = {
    "display_on_leaderboard",
    "display_public_profile",
}


@dataclass(frozen=True)
class EnrollmentToggleUpdate:
    enrollment: Enrollment
    course: Course
    field: str
    enabled: bool


@login_required
@require_POST
def update_enrollment_toggle(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    toggle_update = enrollment_toggle_update_from_post(
        request,
        course,
        enrollment,
    )
    if toggle_update is None:
        payload = {"error": "Unsupported enrollment setting."}
        response = JsonResponse(payload, status=400)
        return response

    update_enrollment_toggle_value(toggle_update)

    payload = {
        "field": toggle_update.field,
        "value": toggle_update.enabled,
    }
    response = JsonResponse(payload)
    return response


def enrollment_toggle_update_from_post(
    request,
    course,
    enrollment,
) -> EnrollmentToggleUpdate | None:
    field = request.POST.get("field", "")
    if field not in ENROLLMENT_TOGGLE_FIELDS:
        return None

    value = request.POST.get("value", "")
    enabled = value.lower() in {"1", "true", "yes", "on"}
    return EnrollmentToggleUpdate(
        enrollment=enrollment,
        course=course,
        field=field,
        enabled=enabled,
    )


def update_enrollment_toggle_value(toggle_update):
    enrollment = toggle_update.enrollment
    previous_display_on_leaderboard = enrollment.display_on_leaderboard
    setattr(enrollment, toggle_update.field, toggle_update.enabled)
    enrollment.save(update_fields=[toggle_update.field])

    if toggle_update.field != "display_on_leaderboard":
        return
    if previous_display_on_leaderboard == toggle_update.enabled:
        return

    invalidate_leaderboard_cache(toggle_update.course.id)


def _render_enrollment_form(request, course, enrollment, form):
    context = {
        "form": form,
        "course": course,
        "enrollment": enrollment,
    }
    response = render(
        request,
        "courses/enrollment.html",
        context,
    )
    return response


def _save_enrollment_form(form, course, enrollment) -> None:
    previous_display_on_leaderboard = enrollment.display_on_leaderboard
    form.save()
    if previous_display_on_leaderboard != form.instance.display_on_leaderboard:
        invalidate_leaderboard_cache(course.id)


def _handle_enrollment_post(request, course, enrollment, course_slug):
    form = EnrollmentForm(
        request.POST,
        instance=enrollment,
        user=request.user,
    )
    if form.is_valid():
        _save_enrollment_form(form, course, enrollment)
        response = redirect("course", course_slug=course_slug)
        return response

    return _render_enrollment_form(request, course, enrollment, form)


@login_required
def enrollment_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)

    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    if request.method == "POST":
        return _handle_enrollment_post(
            request, course, enrollment, course_slug
        )

    form = EnrollmentForm(instance=enrollment, user=request.user)
    return _render_enrollment_form(request, course, enrollment, form)
