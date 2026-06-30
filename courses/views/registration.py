from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.safestring import mark_safe

from course_management.datamailer.sync import (
    send_registration_confirmation_email,
    sync_registration_to_datamailer,
)
from courses.models import (
    CourseRegistration,
    Homework,
    Project,
    RegistrationCampaign,
)
from courses.registration import (
    ordered_countries,
    render_markdown,
    youtube_embed_url,
)

from .forms import CourseRegistrationForm


def campaign_course_is_open(campaign: RegistrationCampaign) -> bool:
    course = campaign.current_course
    if course is None:
        return False

    return (
        Homework.objects.filter(course=course).exists()
        or Project.objects.filter(course=course).exists()
    )


def _active_registration_campaign(
    campaign_slug: str,
) -> RegistrationCampaign:
    return get_object_or_404(
        RegistrationCampaign,
        slug=campaign_slug,
        is_active=True,
    )


def _existing_user_registration(
    request: HttpRequest,
    campaign: RegistrationCampaign,
) -> CourseRegistration | None:
    if not request.user.is_authenticated:
        return None

    email = request.user.email or ""
    email_normalized = email.strip().lower()
    return CourseRegistration.objects.filter(
        campaign=campaign,
        email_normalized=email_normalized,
    ).first()


def _registration_form(
    request: HttpRequest,
    campaign: RegistrationCampaign,
) -> CourseRegistrationForm:
    if request.method == "POST":
        return CourseRegistrationForm(
            request.POST,
            campaign=campaign,
            user=request.user,
        )

    return CourseRegistrationForm(campaign=campaign, user=request.user)


def _save_registration_if_valid(
    form: CourseRegistrationForm,
) -> CourseRegistration | None:
    if not form.is_valid():
        return None

    registration = form.save()
    transaction.on_commit(
        lambda: sync_registration_to_datamailer(registration)
    )
    transaction.on_commit(
        lambda: send_registration_confirmation_email(registration)
    )
    return registration


def _start_course_url(campaign: RegistrationCampaign) -> str:
    if not campaign.current_course_id:
        return ""

    return reverse(
        "course",
        kwargs={"course_slug": campaign.current_course.slug},
    )


def _registration_context(
    campaign: RegistrationCampaign,
    form: CourseRegistrationForm,
    registration: CourseRegistration | None,
) -> dict:
    marketing_content = render_markdown(campaign.marketing_markdown)
    marketing_html = mark_safe(marketing_content)
    video_embed_url = youtube_embed_url(campaign.video_url)
    start_course_url = _start_course_url(campaign)
    country_options = ordered_countries()
    course_is_open = campaign_course_is_open(campaign)

    return {
        "campaign": campaign,
        "course": campaign.current_course,
        "course_is_open": course_is_open,
        "form": form,
        "registration": registration,
        "marketing_html": marketing_html,
        "video_embed_url": video_embed_url,
        "start_course_url": start_course_url,
        "country_options": country_options,
    }


def registration_campaign_view(
    request: HttpRequest,
    campaign_slug: str,
) -> HttpResponse:
    campaign = _active_registration_campaign(campaign_slug)
    existing_registration = _existing_user_registration(
        request, campaign
    )
    form = _registration_form(request, campaign)

    registration = None
    if request.method == "POST":
        registration = _save_registration_if_valid(form)

    context = _registration_context(
        campaign,
        form,
        registration or existing_registration,
    )
    response = render(request, "courses/register.html", context)
    return response
