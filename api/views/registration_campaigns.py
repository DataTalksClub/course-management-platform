from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from api.safety import error_response
from api.utils import parse_json_body, require_methods
from courses.models import Course, CourseRegistration, RegistrationCampaign


CAMPAIGN_FIELDS = {
    "slug",
    "title",
    "edition_label",
    "current_course",
    "is_active",
    "marketing_markdown",
    "meta_description",
    "hero_image_url",
    "video_url",
    "mailchimp_tag_before_switch",
    "mailchimp_tag_after_switch",
    "mailchimp_tag_switch_at",
}


def _datetime_to_iso(value):
    if value is None:
        return None
    return value.isoformat()


def _campaign_to_dict(campaign):
    return {
        "slug": campaign.slug,
        "title": campaign.title,
        "edition_label": campaign.edition_label,
        "current_course": (
            campaign.current_course.slug if campaign.current_course else None
        ),
        "is_active": campaign.is_active,
        "marketing_markdown": campaign.marketing_markdown,
        "meta_description": campaign.meta_description,
        "hero_image_url": campaign.hero_image_url,
        "video_url": campaign.video_url,
        "mailchimp_tag_before_switch": campaign.mailchimp_tag_before_switch,
        "mailchimp_tag_after_switch": campaign.mailchimp_tag_after_switch,
        "mailchimp_tag_switch_at": _datetime_to_iso(
            campaign.mailchimp_tag_switch_at
        ),
        "selected_mailchimp_tag": campaign.selected_mailchimp_tag(),
    }


def _registration_to_dict(registration):
    return {
        "id": registration.id,
        "email": registration.email_normalized,
        "name": registration.name,
        "campaign": registration.campaign.slug,
        "course": registration.course.slug if registration.course else None,
        "country": registration.country,
        "region": registration.region,
        "role": registration.role,
        "role_display": registration.get_role_display(),
        "comment": registration.comment,
        "mailchimp_sync_status": registration.mailchimp_sync_status,
        "mailchimp_tag_used": registration.mailchimp_tag_used,
        "mailchimp_synced_at": _datetime_to_iso(
            registration.mailchimp_synced_at
        ),
        "mailchimp_error": registration.mailchimp_error,
        "created_at": _datetime_to_iso(registration.created_at),
    }


def _normalize_campaign_data(data):
    result = data.copy()

    if "current_course" in result:
        slug = result.pop("current_course")
        if slug in ("", None):
            result["current_course"] = None
        else:
            try:
                result["current_course"] = Course.objects.get(slug=slug)
            except Course.DoesNotExist:
                return None, error_response(
                    f"Course with slug '{slug}' does not exist",
                    "course_not_found",
                    details={"current_course": slug},
                )

    if "mailchimp_tag_switch_at" in result:
        value = result["mailchimp_tag_switch_at"]
        if value in ("", None):
            result["mailchimp_tag_switch_at"] = None
        else:
            parsed = parse_datetime(value)
            if parsed is None:
                return None, error_response(
                    "mailchimp_tag_switch_at must use ISO datetime format",
                    "invalid_datetime",
                    details={"field": "mailchimp_tag_switch_at"},
                )
            result["mailchimp_tag_switch_at"] = parsed

    return result, None


def _validation_error_response(exc):
    if hasattr(exc, "message_dict"):
        details = exc.message_dict
    else:
        details = {"errors": exc.messages}
    return error_response(
        "Registration campaign validation failed",
        "validation_error",
        details=details,
    )


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def registration_campaigns_view(request):
    if request.method == "GET":
        campaigns = RegistrationCampaign.objects.select_related(
            "current_course"
        ).order_by("title", "slug")
        return JsonResponse(
            {"registration_campaigns": [_campaign_to_dict(c) for c in campaigns]}
        )

    data, err = parse_json_body(request)
    if err:
        return err

    unknown_fields = set(data) - CAMPAIGN_FIELDS
    if unknown_fields:
        field = sorted(unknown_fields)[0]
        return error_response(
            f"Cannot set field: {field}",
            "invalid_field",
            details={"field": field},
        )

    data, err = _normalize_campaign_data(data)
    if err:
        return err

    title = data.get("title")
    slug = data.get("slug")
    if not title or not slug:
        return error_response(
            "title and slug are required",
            "missing_required_fields",
        )

    campaign = RegistrationCampaign(**data)
    try:
        campaign.full_clean()
    except ValidationError as exc:
        return _validation_error_response(exc)

    campaign.save()
    return JsonResponse(_campaign_to_dict(campaign), status=201)


@token_required
@csrf_exempt
@require_methods("GET", "PATCH")
def registration_campaign_detail_view(request, campaign_slug):
    campaign = get_object_or_404(
        RegistrationCampaign.objects.select_related("current_course"),
        slug=campaign_slug,
    )

    if request.method == "PATCH":
        data, err = parse_json_body(request)
        if err:
            return err

        unknown_fields = set(data) - CAMPAIGN_FIELDS
        if unknown_fields:
            field = sorted(unknown_fields)[0]
            return error_response(
                f"Cannot update field: {field}",
                "invalid_field",
                details={"field": field},
            )

        data, err = _normalize_campaign_data(data)
        if err:
            return err

        for field, value in data.items():
            setattr(campaign, field, value)

        try:
            campaign.full_clean()
        except ValidationError as exc:
            return _validation_error_response(exc)

        campaign.save()
        return JsonResponse(_campaign_to_dict(campaign))

    return JsonResponse(_campaign_to_dict(campaign))


def _count_by(queryset, field):
    return [
        {"value": item[field] or "", "count": item["count"]}
        for item in queryset.values(field).annotate(count=Count("id")).order_by(
            "-count",
            field,
        )
    ]


@token_required
@require_methods("GET")
def registration_campaign_registrations_view(request, campaign_slug):
    campaign = get_object_or_404(RegistrationCampaign, slug=campaign_slug)
    registrations = CourseRegistration.objects.filter(
        campaign=campaign
    ).select_related("campaign", "course")

    search = request.GET.get("q", "").strip()
    if search:
        registrations = registrations.filter(
            Q(email_normalized__icontains=search)
            | Q(name__icontains=search)
        )

    for field in ("role", "country", "region", "mailchimp_sync_status"):
        value = request.GET.get(field, "").strip()
        if value:
            registrations = registrations.filter(**{field: value})

    stats_base = CourseRegistration.objects.filter(campaign=campaign)
    stats = {
        "total": stats_base.count(),
        "by_role": _count_by(stats_base, "role"),
        "by_country": _count_by(stats_base, "country"),
        "by_region": _count_by(stats_base, "region"),
        "by_mailchimp_sync_status": _count_by(
            stats_base,
            "mailchimp_sync_status",
        ),
    }

    try:
        limit = min(int(request.GET.get("limit", 100)), 500)
    except ValueError:
        return error_response(
            "limit must be an integer",
            "invalid_limit",
            details={"field": "limit"},
        )
    return JsonResponse(
        {
            "campaign": _campaign_to_dict(campaign),
            "stats": stats,
            "registrations": [
                _registration_to_dict(registration)
                for registration in registrations.order_by("-created_at")[:limit]
            ],
        }
    )
