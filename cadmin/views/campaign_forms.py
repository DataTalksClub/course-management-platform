import re

from dataclasses import dataclass

from django.contrib import messages
from django.shortcuts import redirect

from courses.models.course import Course
from cadmin.forms import RegistrationCampaignForm

from .campaign_datamailer import (
    datamailer_campaign_context,
    handle_datamailer_campaign_action,
)


@dataclass(frozen=True)
class CampaignEditPostResult:
    response: object
    form: object
    datamailer_preview: object


_TRAILING_YEAR_RE = re.compile(r"[\s_-]*(\d{4})\s*$")


def split_trailing_year(text):
    """Split a trailing 4-digit year off the end of ``text``."""
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
    title_base, title_year = split_trailing_year(course.title)
    slug_base, slug_year = split_trailing_year(course.slug)
    year = title_year or slug_year

    initial["slug"] = slug_base or course.slug

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


def handle_campaign_datamailer_post(request, campaign):
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


def handle_campaign_form_post(request, campaign):
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


def campaign_edit_context(campaign, form, datamailer_preview):
    datamailer_context = datamailer_campaign_context(campaign)
    context = {
        "form": form,
        "campaign": campaign,
        "course": campaign.current_course,
        "page_title": "Edit registration landing page",
        "submit_label": "Save changes",
        "datamailer_preview": datamailer_preview,
    }
    context.update(datamailer_context)
    return context
