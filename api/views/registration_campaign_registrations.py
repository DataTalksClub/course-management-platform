from django.db.models import Count, Q

from api.safety import error_response
from api.views.registration_campaign_serializers import (
    campaign_to_dict,
    registration_to_dict,
)
from courses.models import CourseRegistration


def registration_campaign_registrations_payload(campaign, params):
    registrations = filtered_registrations(campaign, params)
    stats = registration_campaign_stats(campaign)
    limit, err = registration_limit(params)
    if err:
        return None, err

    payload = registration_list_payload(campaign, registrations, stats, limit)
    return payload, None


def filtered_registrations(campaign, params):
    registrations = campaign_registrations_queryset(campaign)
    search_query = params.get("q", "")
    registrations = apply_registration_search(
        registrations,
        search_query,
    )
    return apply_registration_exact_filters(registrations, params)


def campaign_registrations_queryset(campaign):
    return CourseRegistration.objects.filter(
        campaign=campaign
    ).select_related("campaign", "course")


def apply_registration_search(queryset, search):
    search = search.strip()
    if not search:
        return queryset

    return queryset.filter(
        Q(email_normalized__icontains=search) | Q(name__icontains=search)
    )


def apply_registration_exact_filters(queryset, params):
    filter_fields = ("role", "country", "region")
    for field in filter_fields:
        value = params.get(field, "").strip()
        if value:
            queryset = queryset.filter(**{field: value})
    return queryset


def registration_campaign_stats(campaign):
    stats_base = CourseRegistration.objects.filter(campaign=campaign)
    return {
        "total": stats_base.count(),
        "by_role": count_by(stats_base, "role"),
        "by_country": count_by(stats_base, "country"),
        "by_region": count_by(stats_base, "region"),
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
        return min(limit, 500), None
    except ValueError:
        return None, error_response(
            "limit must be an integer",
            "invalid_limit",
            details={"field": "limit"},
        )


def registration_list_payload(campaign, registrations, stats, limit):
    registration_records = []
    ordered_registrations = registrations.order_by("-created_at")[:limit]
    for registration in ordered_registrations:
        registration_record = registration_to_dict(registration)
        registration_records.append(registration_record)

    campaign_data = campaign_to_dict(campaign)
    return {
        "campaign": campaign_data,
        "stats": stats,
        "registrations": registration_records,
    }
