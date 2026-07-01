from dataclasses import dataclass

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


def campaign_registration_queryset(campaign):
    return CourseRegistration.objects.filter(
        campaign=campaign
    ).select_related("campaign", "course", "user")


def campaign_registration_filters(request):
    raw_role = request.GET.get("role", "")
    raw_country = request.GET.get("country", "")
    raw_region = request.GET.get("region", "")
    role = raw_role.strip()
    country = raw_country.strip()
    region = raw_region.strip()
    return {
        "role": role,
        "country": country,
        "region": region,
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
    )


def campaign_registrations_context(data):
    page_range = data.registrations_page.paginator.get_elided_page_range(
        data.registrations_page.number
    )
    metrics = registration_campaign_metrics(data.campaign)
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
    }


def campaign_registrations_context_data(request, campaign):
    filters = campaign_registration_filters(request)
    raw_search_query = request.GET.get("q", "")
    search_query = raw_search_query.strip()

    registrations = campaign_registration_queryset(campaign)
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
