from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.safestring import mark_safe

from course_management.datamailer import sync_registration_to_datamailer
from course_management.mailchimp import sync_registration_to_mailchimp
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


def registration_campaign_view(
    request: HttpRequest,
    campaign_slug: str,
) -> HttpResponse:
    campaign = get_object_or_404(
        RegistrationCampaign,
        slug=campaign_slug,
        is_active=True,
    )
    course_is_open = campaign_course_is_open(campaign)
    registration = None
    existing_registration = None

    if request.user.is_authenticated:
        existing_registration = CourseRegistration.objects.filter(
            campaign=campaign,
            email_normalized=(request.user.email or "").strip().lower(),
        ).first()

    if request.method == "POST":
        form = CourseRegistrationForm(
            request.POST,
            campaign=campaign,
            user=request.user,
        )
        if form.is_valid():
            registration = form.save()
            transaction.on_commit(
                lambda: sync_registration_to_mailchimp(registration)
            )
            transaction.on_commit(
                lambda: sync_registration_to_datamailer(registration)
            )
    else:
        form = CourseRegistrationForm(
            campaign=campaign, user=request.user
        )

    start_course_url = ""
    if campaign.current_course_id:
        start_course_url = reverse(
            "course",
            kwargs={"course_slug": campaign.current_course.slug},
        )

    context = {
        "campaign": campaign,
        "course": campaign.current_course,
        "course_is_open": course_is_open,
        "form": form,
        "registration": registration or existing_registration,
        "marketing_html": mark_safe(
            render_markdown(campaign.marketing_markdown)
        ),
        "video_embed_url": youtube_embed_url(campaign.video_url),
        "start_course_url": start_course_url,
        "country_options": ordered_countries(),
    }
    return render(request, "courses/register.html", context)
