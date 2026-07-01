import re

from dataclasses import dataclass

from django.contrib import messages
from django.core.paginator import Page
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import (
    Course,
    CourseRegistration,
    RegistrationCampaign,
)
from cadmin.forms import RegistrationCampaignForm
from .campaign_datamailer import (
    datamailer_campaign_context,
    handle_datamailer_campaign_action,
)
from .helpers import (
    count_by,
    paginate_queryset,
    pagination_querystring,
    staff_required,
)

@dataclass(frozen=True)
class CampaignRegistrationsContextData:
    request: HttpRequest
    campaign: RegistrationCampaign
    registrations_page: Page
    filters: dict
    search_query: str


@dataclass(frozen=True)
class CampaignEditPostResult:
    response: object
    form: object
    datamailer_preview: object


def registration_campaign_metrics(campaign):
    registrations = CourseRegistration.objects.filter(campaign=campaign)
    return {
        "campaign": campaign,
        "total": registrations.count(),
        "by_role": count_by(registrations, "role"),
        "by_country": count_by(registrations, "country"),
        "by_region": count_by(registrations, "region"),
    }


_TRAILING_YEAR_RE = re.compile(r"[\s_-]*(\d{4})\s*$")


def _split_trailing_year(text):
    """Split a trailing 4-digit year off the end of ``text``.

    Returns ``(base, year)`` where ``base`` has the year (and any joining
    separator) removed. ``year`` is an empty string when none is found.
    """
    text_value = text or ""
    match = _TRAILING_YEAR_RE.search(text_value)
    if not match:
        base = text_value.strip()
        return base, ""
    base = text_value[: match.start()]
    stripped_base = base.strip()
    stripped_base = stripped_base.rstrip("-_ ")
    stripped_base = stripped_base.strip()
    year = match.group(1)
    return stripped_base, year


def campaign_initial_course(request):
    raw_course_slug = request.GET.get("course", "")
    course_slug = raw_course_slug.strip()
    if not course_slug:
        return None

    courses = Course.objects.filter(slug=course_slug)
    course = courses.first()
    return course


def campaign_initial_from_course(course):
    initial = {"current_course": course}
    title_base, title_year = _split_trailing_year(course.title)
    slug_base, slug_year = _split_trailing_year(course.slug)
    year = title_year or slug_year

    # Stable, year-agnostic public URL ("ml-zoomcamp-2025" -> "ml-zoomcamp").
    initial["slug"] = slug_base or course.slug

    # Title without the edition year ("Machine Learning Zoomcamp 2025" ->
    # "Machine Learning Zoomcamp"); the year becomes the edition label.
    if title_base:
        initial["title"] = title_base
    if year:
        initial["edition_label"] = f"{year} cohort"

    return initial


def campaign_form_initial(request):
    course = campaign_initial_course(request)
    if course is None:
        return {}

    return campaign_initial_from_course(course)


def campaign_form_course(form):
    course = form.initial.get("current_course")
    if course is not None:
        return course

    if form.is_bound:
        course_id = form.data.get("current_course")
    else:
        course_id = ""
    if not course_id:
        return None

    courses = Course.objects.filter(pk=course_id)
    course = courses.first()
    return course


@staff_required
def campaign_create(request):
    if request.method == "POST":
        form = RegistrationCampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save()
            messages.success(
                request, "Registration landing page created."
            )
            response = redirect(
                "cadmin_campaign_edit", campaign_slug=campaign.slug
            )
            return response
    else:
        initial = campaign_form_initial(request)
        form = RegistrationCampaignForm(initial=initial)

    course = campaign_form_course(form)
    context = {
        "form": form,
        "campaign": None,
        "course": course,
        "page_title": "Create registration landing page",
        "submit_label": "Create landing page",
    }
    response = render(request, "cadmin/campaign_form.html", context)
    return response


def _handle_campaign_datamailer_post(request, campaign):
    datamailer_preview, should_redirect = (
        handle_datamailer_campaign_action(request, campaign)
    )
    if should_redirect:
        response = redirect(
            "cadmin_campaign_edit",
            campaign_slug=campaign.slug,
        )
        return CampaignEditPostResult(
            response=response,
            form=None,
            datamailer_preview=None,
        )

    form = RegistrationCampaignForm(instance=campaign)
    return CampaignEditPostResult(
        response=None,
        form=form,
        datamailer_preview=datamailer_preview,
    )


def _handle_campaign_form_post(request, campaign):
    form = RegistrationCampaignForm(request.POST, instance=campaign)
    if form.is_valid():
        campaign = form.save()
        messages.success(request, "Registration landing page saved.")
        response = redirect(
            "cadmin_campaign_edit",
            campaign_slug=campaign.slug,
        )
        return CampaignEditPostResult(
            response=response,
            form=None,
            datamailer_preview=None,
        )
    return CampaignEditPostResult(
        response=None,
        form=form,
        datamailer_preview=None,
    )


def _campaign_edit_context(campaign, form, datamailer_preview):
    return {
        "form": form,
        "campaign": campaign,
        "course": campaign.current_course,
        "page_title": "Edit registration landing page",
        "submit_label": "Save changes",
        "datamailer_preview": datamailer_preview,
        **datamailer_campaign_context(campaign),
    }


@staff_required
def campaign_edit(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )

    if request.method == "POST":
        if request.POST.get("datamailer_action"):
            post_result = _handle_campaign_datamailer_post(
                request,
                campaign,
            )
        else:
            post_result = _handle_campaign_form_post(request, campaign)
        if post_result.response:
            return post_result.response
        form = post_result.form
        datamailer_preview = post_result.datamailer_preview
    else:
        form = RegistrationCampaignForm(instance=campaign)
        datamailer_preview = None

    context = _campaign_edit_context(
        campaign,
        form,
        datamailer_preview,
    )
    response = render(request, "cadmin/campaign_form.html", context)
    return response


def _campaign_registration_queryset(campaign):
    return CourseRegistration.objects.filter(
        campaign=campaign
    ).select_related("campaign", "course", "user")


def _campaign_registration_filters(request):
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


def _apply_campaign_registration_filters(registrations, filters):
    for field, value in filters.items():
        if value:
            registrations = registrations.filter(**{field: value})
    return registrations


def _apply_campaign_registration_search(registrations, search_query):
    if not search_query:
        return registrations

    return registrations.filter(
        Q(email_normalized__icontains=search_query)
        | Q(name__icontains=search_query)
    )


def _campaign_registrations_context(data):
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


@staff_required
def campaign_registrations(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )
    filters = _campaign_registration_filters(request)
    raw_search_query = request.GET.get("q", "")
    search_query = raw_search_query.strip()

    registrations = _campaign_registration_queryset(campaign)
    registrations = _apply_campaign_registration_filters(
        registrations, filters
    )
    registrations = _apply_campaign_registration_search(
        registrations, search_query
    )
    registrations_page = paginate_queryset(request, registrations, 50)
    context_data = CampaignRegistrationsContextData(
        request=request,
        campaign=campaign,
        registrations_page=registrations_page,
        filters=filters,
        search_query=search_query,
    )
    context = _campaign_registrations_context(context_data)
    response = render(
        request, "cadmin/campaign_registrations.html", context
    )
    return response
