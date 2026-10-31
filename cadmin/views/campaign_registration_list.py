from dataclasses import dataclass
from urllib.parse import urlencode

from django.core.paginator import Page
from django.db.models import Q
from django.http import HttpRequest

from courses.models.course import CourseRegistration, RegistrationCampaign

from .campaign_metrics import registration_campaign_metrics
from .helpers import paginate_queryset, pagination_querystring


@dataclass(frozen=True)
class CampaignRegistrationsContextData:
    request: HttpRequest
    campaign: RegistrationCampaign
    registrations_page: Page
    filters: dict
    search_query: str


def campaign_registration_filters(request):
    raw_role = request.GET.get("role", "")
    raw_country = request.GET.get("country", "")
    raw_region = request.GET.get("region", "")
    raw_status = request.GET.get("status", "")
    role = raw_role.strip()
    country = raw_country.strip()
    region = raw_region.strip()
    status = raw_status.strip()
    valid_statuses = {
        choice for choice, _ in CourseRegistration.Status.choices
    }
    if status not in valid_statuses:
        status = ""
    return {
        "role": role,
        "country": country,
        "region": region,
        "status": status,
    }


def apply_campaign_registration_filters(registrations, filters):
    for field, value in filters.items():
        if value:
            criteria = {field: value}
            registrations = registrations.filter(**criteria)
    return registrations


def apply_campaign_registration_search(registrations, search_query):
    if not search_query:
        return registrations

    return registrations.filter(
        Q(email_normalized__icontains=search_query)
        | Q(name__icontains=search_query)
        | Q(company_name__icontains=search_query)
        | Q(experience__icontains=search_query)
        | Q(why_join__icontains=search_query)
    )


def campaign_registrations_context(data):
    page_range = data.registrations_page.paginator.get_elided_page_range(
        data.registrations_page.number
    )
    metrics = registration_campaign_metrics(data.campaign)
    course = data.campaign.current_course
    needs_approval = bool(
        course is not None and course.requires_registration_approval
    )
    querystring = pagination_querystring(data.request)

    return {
        "campaign": data.campaign,
        "course": data.campaign.current_course,
        "registrations_page": data.registrations_page,
        "page_range": page_range,
        "metrics": metrics,
        "filters": data.filters,
        "search_query": data.search_query,
        "pagination_querystring": querystring,
        "status_choices": CourseRegistration.Status.choices,
        "needs_approval": needs_approval,
        "status_tabs": status_tabs(data, metrics, needs_approval),
    }


def status_tabs(data, metrics, needs_approval):
    """Tabs with counts, keeping the other active filters in each link."""
    if not needs_approval:
        return []
    counts = {row["status"]: row["count"] for row in metrics["by_status"]}
    base = {
        key: value
        for key, value in data.request.GET.items()
        if key not in ("status", "page") and value
    }
    labels = dict(CourseRegistration.Status.choices)
    tabs = [("", "All", metrics["total"])]
    for value in ("pending", "approved", "rejected"):
        tabs.append((value, labels.get(value, value), counts.get(value, 0)))
    result = []
    for value, label, count in tabs:
        params = dict(base)
        if value:
            params["status"] = value
        result.append({
            "label": label,
            "count": count,
            "active": data.filters["status"] == value,
            "query": urlencode(params),
        })
    return result


def campaign_registrations_context_data(request, campaign):
    filters = campaign_registration_filters(request)
    course = campaign.current_course
    if course is None or not course.requires_registration_approval:
        # Every registration defaults to "pending"; without an approval step
        # that status is meaningless, so stale ?status= links list everyone.
        filters["status"] = ""
    raw_search_query = request.GET.get("q", "")
    search_query = raw_search_query.strip()

    registrations = CourseRegistration.objects.filter(
        campaign=campaign
    ).select_related("campaign", "course", "user")
    registrations = apply_campaign_registration_filters(
        registrations, filters
    )
    registrations = apply_campaign_registration_search(
        registrations, search_query
    )
    registrations_page = paginate_queryset(request, registrations, 50)
    return CampaignRegistrationsContextData(
        request=request,
        campaign=campaign,
        registrations_page=registrations_page,
        filters=filters,
        search_query=search_query,
    )
