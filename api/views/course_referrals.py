from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from api.safety import require_staff_token
from api.utils import require_methods
from courses.leaderboard import update_leaderboard
from courses.models import Course, CourseRegistration, Enrollment, ReferralReward


@token_required
@require_methods("GET")
def course_referrals_view(request, course_slug):
    """Return aggregate referral counts for a course (staff-only, no PII)."""
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    rewards = ReferralReward.objects.filter(referred__course=course)
    successful_referrals_count = rewards.count()
    unique_referrers_count = rewards.values("referrer_id").distinct().count()
    total_bonus_points_awarded = (
        rewards.aggregate(total=Sum("points"))["total"] or 0
    )
    referred_registrations_count = CourseRegistration.objects.filter(
        course=course,
        referred_by__isnull=False,
    ).count()
    enrollments_with_bonus_points = Enrollment.objects.filter(
        course=course,
        bonus_points__gt=0,
    ).count()

    return JsonResponse(
        {
            "course": course.slug,
            "successful_referrals_count": successful_referrals_count,
            "unique_referrers_count": unique_referrers_count,
            "total_bonus_points_awarded": total_bonus_points_awarded,
            "referred_registrations_count": referred_registrations_count,
            "enrollments_with_bonus_points": enrollments_with_bonus_points,
        }
    )


@token_required
@csrf_exempt
@require_methods("POST")
def course_leaderboard_refresh_view(request, course_slug):
    """Recompute leaderboard scores, positions, and cache version (staff-only)."""
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    update_leaderboard(course)
    course.refresh_from_db(fields=["leaderboard_cache_version"])

    return JsonResponse(
        {
            "course": course.slug,
            "leaderboard_cache_version": course.leaderboard_cache_version,
            "updated": True,
        }
    )
