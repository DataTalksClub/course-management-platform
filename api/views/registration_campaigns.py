from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from api.safety import error_response, require_staff_token
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
}


def _datetime_to_iso(value):
    if value is None:
        return None
    return value.isoformat()


def _campaign_to_dict(campaign):
    current_course = campaign.current_course
    current_course_slug = None
    if current_course:
        current_course_slug = current_course.slug
    return {
        "slug": campaign.slug,
        "title": campaign.title,
        "edition_label": campaign.edition_label,
        "current_course": current_course_slug,
        "is_active": campaign.is_active,
        "marketing_markdown": campaign.marketing_markdown,
        "meta_description": campaign.meta_description,
        "hero_image_url": campaign.hero_image_url,
        "video_url": campaign.video_url,
    }


def _registration_to_dict(registration):
    course = registration.course
    course_slug = None
    if course:
        course_slug = course.slug
    return {
        "id": registration.id,
        "email": registration.email_normalized,
        "name": registration.name,
        "campaign": registration.campaign.slug,
        "course": course_slug,
        "country": registration.country,
        "region": registration.region,
        "role": registration.role,
        "role_display": registration.get_role_display(),
        "comment": registration.comment,
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


def _invalid_campaign_field_response(field, action):
    return error_response(
        f"Cannot {action} field: {field}",
        "invalid_field",
        details={"field": field},
    )


def _campaign_field_error(data, action):
    unknown_fields = set(data) - CAMPAIGN_FIELDS
    if not unknown_fields:
        return None

    field = sorted(unknown_fields)[0]
    return _invalid_campaign_field_response(field, action)


def _campaigns_list_response():
    campaigns = RegistrationCampaign.objects.select_related(
        "current_course"
    ).order_by("title", "slug")
    campaign_records = []
    for campaign in campaigns:
        campaign_record = _campaign_to_dict(campaign)
        campaign_records.append(campaign_record)

    payload = {"registration_campaigns": campaign_records}
    response = JsonResponse(payload)
    return response


def _clean_campaign_payload(request, *, action):
    data, err = parse_json_body(request)
    if err:
        return None, err

    err = _campaign_field_error(data, action)
    if err:
        return None, err

    return _normalize_campaign_data(data)


def _save_campaign(campaign):
    try:
        campaign.full_clean()
    except ValidationError as exc:
        return _validation_error_response(exc)

    campaign.save()
    return None


def _campaign_required_fields_error(data):
    title = data.get("title")
    slug = data.get("slug")
    if title and slug:
        return None

    error = error_response(
        "title and slug are required",
        "missing_required_fields",
    )
    return error


def _created_campaign(data):
    error = _campaign_required_fields_error(data)
    if error:
        return None, error

    campaign = RegistrationCampaign(**data)
    error = _save_campaign(campaign)
    if error:
        return None, error

    return campaign, None


def _campaign_create_response(request):
    data, err = _clean_campaign_payload(request, action="set")
    if err:
        return err

    campaign, error = _created_campaign(data)
    if error:
        return error

    campaign_data = _campaign_to_dict(campaign)
    response = JsonResponse(campaign_data, status=201)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def registration_campaigns_view(request):
    if request.method == "GET":
        return _campaigns_list_response()

    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    return _campaign_create_response(request)


def _campaign_patch_response(request, campaign):
    data, err = _clean_campaign_payload(request, action="update")
    if err:
        return err

    for field, value in data.items():
        setattr(campaign, field, value)

    err = _save_campaign(campaign)
    if err:
        return err

    campaign_data = _campaign_to_dict(campaign)
    response = JsonResponse(campaign_data)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "PATCH")
def registration_campaign_detail_view(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )

    if request.method == "PATCH":
        staff_error = require_staff_token(request)
        if staff_error:
            return staff_error

        return _campaign_patch_response(request, campaign)

    campaign_data = _campaign_to_dict(campaign)
    response = JsonResponse(campaign_data)
    return response


def _count_by(queryset, field):
    counts = []
    group_count = Count("id")
    grouped_values = queryset.values(field).annotate(count=group_count).order_by(
        "-count",
        field,
    )
    for item in grouped_values:
        count_record = {"value": item[field] or "", "count": item["count"]}
        counts.append(count_record)
    return counts


def _campaign_registrations_queryset(campaign):
    return CourseRegistration.objects.filter(
        campaign=campaign
    ).select_related("campaign", "course")


def _apply_registration_search(queryset, search):
    search = search.strip()
    if not search:
        return queryset

    return queryset.filter(
        Q(email_normalized__icontains=search) | Q(name__icontains=search)
    )


def _apply_registration_exact_filters(queryset, params):
    filter_fields = ("role", "country", "region")
    for field in filter_fields:
        value = params.get(field, "").strip()
        if value:
            queryset = queryset.filter(**{field: value})
    return queryset


def _filtered_registrations(campaign, params):
    registrations = _campaign_registrations_queryset(campaign)
    search_query = params.get("q", "")
    registrations = _apply_registration_search(
        registrations,
        search_query,
    )
    return _apply_registration_exact_filters(registrations, params)


def _registration_campaign_stats(campaign):
    stats_base = CourseRegistration.objects.filter(campaign=campaign)
    return {
        "total": stats_base.count(),
        "by_role": _count_by(stats_base, "role"),
        "by_country": _count_by(stats_base, "country"),
        "by_region": _count_by(stats_base, "region"),
    }


def _registration_limit(params):
    try:
        raw_limit = params.get("limit", 100)
        limit = int(raw_limit)
        return min(limit, 500), None
    except ValueError:
        return None, error_response(
            "limit must be an integer",
            "invalid_limit",
            details={"field": "limit"},
        )


def _registration_list_payload(campaign, registrations, stats, limit):
    registration_records = []
    ordered_registrations = registrations.order_by("-created_at")[:limit]
    for registration in ordered_registrations:
        registration_record = _registration_to_dict(registration)
        registration_records.append(registration_record)

    campaign_data = _campaign_to_dict(campaign)
    return {
        "campaign": campaign_data,
        "stats": stats,
        "registrations": registration_records,
    }


@token_required
@require_methods("GET")
def registration_campaign_registrations_view(request, campaign_slug):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    campaign = get_object_or_404(RegistrationCampaign, slug=campaign_slug)
    registrations = _filtered_registrations(campaign, request.GET)
    stats = _registration_campaign_stats(campaign)
    limit, err = _registration_limit(request.GET)
    if err:
        return err

    payload = _registration_list_payload(campaign, registrations, stats, limit)
    response = JsonResponse(payload)
    return response
