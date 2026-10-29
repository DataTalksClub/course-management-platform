from functools import partial

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from course_management.relay.registration import (
    sync_registration_to_relay,
)
from course_management.relay.notifications import (
    send_registration_confirmation_email,
)
from course_management.observability import record_event
from courses import cross_sell
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
    registration_email_taken,
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

    try:
        # Duplicate validation can race another request's insert. Roll back
        # the failed save before querying, keeping the outer transaction usable.
        with transaction.atomic():
            registration = form.save()
    except IntegrityError:
        if not registration_email_taken(
            form.campaign,
            normalized_registration_email(form.cleaned_data["email"]),
        ):
            raise
        form.add_error("email", "You have already registered for this course.")
        return None
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


def _cross_sell_context(
    request: HttpRequest,
    campaign: RegistrationCampaign,
    registration: CourseRegistration | None,
) -> dict:
    if registration is None:
        return {"cross_sell_suggestions": [], "cross_sell_registered": []}

    shown = cross_sell.suggestions_for_registration(registration)
    cross_sell.record_impression(request, campaign, shown)
    registered_slugs = request.session.pop(
        "cross_sell_registered", {}
    ).get(str(campaign.pk), [])
    registered = list(
        RegistrationCampaign.objects.filter(slug__in=registered_slugs)
    )
    return {
        "cross_sell_suggestions": shown,
        "cross_sell_has_one_click": any(s.one_click for s in shown),
        "cross_sell_registered": registered,
    }


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
    if request.method == "GET":
        cross_sell.remember_link_click(request, campaign)
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
            cross_sell.attribute_link_registration(request, registration)
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

    shown_registration = registration or existing_registration
    context = _registration_context(
        campaign,
        form,
        shown_registration,
    )
    context.update(
        _cross_sell_context(request, campaign, shown_registration)
    )
    response = render(request, "courses/register.html", context)
    return response


@require_POST
def registration_cross_sell_view(
    request: HttpRequest,
    campaign_slug: str,
) -> HttpResponse:
    """One-click registration for suggested courses (no re-entry).

    The source is the visitor's own registration on ``campaign_slug``
    (account, or the anonymous session that just submitted the form).
    """
    campaign = _active_registration_campaign(campaign_slug)
    source = _existing_user_registration(request, campaign)
    if source is not None:
        slugs = request.POST.getlist("campaigns")
        single = request.POST.get("campaign", "")
        if single:
            slugs = [single]
        created = cross_sell.register_suggested(source, slugs, request)
        if created:
            registered = request.session.get("cross_sell_registered", {})
            registered[str(campaign.pk)] = [
                registration.campaign.slug for registration in created
            ]
            request.session["cross_sell_registered"] = registered
    return redirect("registration_campaign", campaign_slug=campaign.slug)
