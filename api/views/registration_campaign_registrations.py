from django.db.models import Count, Q

from api.safety import error_response
from api.views.registration_campaign_serializers import (
    campaign_to_dict,
    registration_to_dict,
)
from courses.models.course import CourseRegistration

MAX_LIMIT = 500
BOOLEAN_FILTER_FIELDS = ("accepted_nebius_sharing",)
TRUE_VALUES = ("true", "1", "yes")
FALSE_VALUES = ("false", "0", "no")


def registration_campaign_registrations_payload(campaign, params):
    registrations = filtered_registrations(campaign, params)
    stats = registration_campaign_stats(campaign)
    limit, err = registration_limit(params)
    if err:
        return None, err
    offset, err = registration_offset(params)
    if err:
        return None, err

    payload = registration_list_payload(
        campaign, registrations, stats, limit, offset
    )
    return payload, None


def filtered_registrations(campaign, params):
    registrations = CourseRegistration.objects.filter(
        campaign=campaign
    ).select_related("campaign", "course")
    search_query = params.get("q", "")
    registrations = apply_registration_search(
        registrations,
        search_query,
    )
    return apply_registration_exact_filters(registrations, params)


def apply_registration_search(queryset, search):
    search = search.strip()
    if not search:
        return queryset

    return queryset.filter(
        Q(email_normalized__icontains=search) | Q(name__icontains=search)
    )


def apply_registration_exact_filters(queryset, params):
    for field in ("role", "country", "region", "status"):
        value = params.get(field, "").strip()
        if value:
            queryset = queryset.filter(**{field: value})
    for field in BOOLEAN_FILTER_FIELDS:
        value = params.get(field, "").strip().lower()
        if value in TRUE_VALUES:
            queryset = queryset.filter(**{field: True})
        elif value in FALSE_VALUES:
            queryset = queryset.filter(**{field: False})
    return queryset


def registration_campaign_stats(campaign):
    stats_base = CourseRegistration.objects.filter(campaign=campaign)
    total = stats_base.count()
    by_role = count_by(stats_base, "role")
    by_country = count_by(stats_base, "country")
    by_region = count_by(stats_base, "region")
    return {
        "total": total,
        "by_role": by_role,
        "by_country": by_country,
        "by_region": by_region,
    }


def count_by(queryset, field):
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


def registration_limit(params):
    try:
        raw_limit = params.get("limit", 100)
        limit = int(raw_limit)
        capped_limit = min(limit, MAX_LIMIT)
        return capped_limit, None
    except ValueError:
        error = error_response(
            "limit must be an integer",
            "invalid_limit",
            details={"field": "limit"},
        )
        return None, error


def registration_offset(params):
    try:
        offset = int(params.get("offset", 0))
    except ValueError:
        offset = -1
    if offset < 0:
        error = error_response(
            "offset must be a non-negative integer",
            "invalid_offset",
            details={"field": "offset"},
        )
        return None, error
    return offset, None


def registration_list_payload(campaign, registrations, stats, limit, offset=0):
    registration_records = []
    # The id tie-breaker keeps offset pages stable when created_at collides.
    ordered_registrations = registrations.order_by("-created_at", "-id")
    page = ordered_registrations[offset:offset + limit]
    for registration in page:
        registration_record = registration_to_dict(registration)
        registration_records.append(registration_record)

    campaign_data = campaign_to_dict(campaign)
    return {
        "campaign": campaign_data,
        "stats": stats,
        "count": registrations.count(),
        "limit": limit,
        "offset": offset,
        "registrations": registration_records,
    }
