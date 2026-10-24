from functools import partial

from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.safestring import mark_safe

from course_management.relay.registration import (
    sync_registration_to_relay,
)
from course_management.relay.notifications import (
    send_registration_confirmation_email,
)
from course_management.observability import record_event
from courses.models.course import (
    CourseRegistration,
    RegistrationCampaign,
)
from courses.models.homework import Homework
from courses.models.project import Project
from courses.registration import (
    ordered_countries,
    render_markdown,
    youtube_embed_url,
)
from courses.registration_confirmation import issue_confirmation_token

from .registration_form import (
    CourseRegistrationForm,
    normalized_registration_email,
)


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
        registration_id = request.session.get(
            "registration_pending", {}
        ).get(str(campaign.pk))
        return CourseRegistration.objects.filter(
            pk=registration_id, campaign=campaign
        ).first()

    email = request.user.email or ""
    email_stripped = email.strip()
    email_normalized = email_stripped.lower()
    return CourseRegistration.objects.filter(
        Q(user=request.user) | Q(email_normalized=email_normalized),
        campaign=campaign,
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


@transaction.atomic
def _save_registration_if_valid(
    form: CourseRegistrationForm,
) -> CourseRegistration | None:
    if not form.is_valid():
        return None

    registration = form.save()
    # New registrations start pending email confirmation: issue the
    # token now so the Relay confirmation email carries the link.
    issue_confirmation_token(registration)
    sync_callback = partial(
        sync_registration_to_relay,
        registration,
    )
    email_callback = partial(
        send_registration_confirmation_email,
        registration,
    )
    transaction.on_commit(sync_callback)
    transaction.on_commit(email_callback)
    return registration


def _start_course_url(campaign: RegistrationCampaign) -> str:
    if not campaign.current_course_id:
        return ""

    return reverse(
        "course",
        kwargs={"course_slug": campaign.current_course.slug},
    )


def _pending_duplicate_registration(
    request: HttpRequest,
    campaign: RegistrationCampaign,
    form: CourseRegistrationForm,
) -> CourseRegistration | None:
    """Recover the pending block after a refresh/double POST.

    Only for anonymous users whose POST failed on the duplicate-email
    error while the existing registration is still unconfirmed.
    """
    if request.user.is_authenticated or "email" not in form.errors:
        return None
    email_error = " ".join(str(error) for error in form.errors["email"])
    if "already registered" not in email_error:
        return None
    normalized = normalized_registration_email(
        request.POST.get("email", "")
    )
    registration_id = request.session.get(
        "registration_pending", {}
    ).get(str(campaign.pk))
    if not normalized or not registration_id:
        return None
    return (
        CourseRegistration.objects.filter(
            campaign=campaign,
            pk=registration_id,
            email_normalized=normalized,
            email_confirmed=False,
        )
        .select_related("campaign", "course")
        .first()
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
    course = campaign.current_course
    registration_wall = bool(
        course is not None
        and getattr(course, "requires_registration_approval", False)
    )

    return {
        "campaign": campaign,
        "course": course,
        "course_is_open": course_is_open,
        "registration_wall": registration_wall,
        "signup_count": campaign.registrations.count(),
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
    saved_fresh = False
    if request.method == "POST":
        registration = _save_registration_if_valid(form)
        saved_fresh = registration is not None
        if saved_fresh:
            pending = request.session.get("registration_pending", {})
            pending[str(campaign.pk)] = registration.pk
            request.session["registration_pending"] = pending
        if registration is None:
            # Refresh-after-POST (or double submit) re-posts the same
            # address: surface the pending confirmation block with its
            # resend/fix options instead of only a duplicate error.
            registration = _pending_duplicate_registration(
                request, campaign, form
            )
        if saved_fresh:
            course_slug = ""
            if registration.course_id:
                course_slug = registration.course.slug
            record_event(
                "registration.submitted",
                request=request,
                user=request.user,
                properties={
                    "campaign_slug": campaign.slug,
                    "course_slug": course_slug,
                    "registration_id": registration.id,
                    "accepted_newsletter": registration.accepted_newsletter,
                },
            )

    context = _registration_context(
        campaign,
        form,
        registration or existing_registration,
    )
    response = render(request, "courses/register.html", context)
    return response
