"""Suggest other courses after a registration (cross-sell).

Relevance rule (docs/cross-sell.md), deterministic:

1. Candidates are active registration campaigns that are not excluded
   (``exclude_from_suggestions`` or ``CROSS_SELL_EXCLUDED_CAMPAIGNS``),
   are not the source campaign or its edition, and whose edition is not
   finished. Campaigns without an edition yet ("next cohort") qualify.
2. Campaigns the person is already registered for (same user or email)
   or whose edition they are enrolled in are dropped.
3. Curated ``suggested_campaigns`` of the source come first, then every
   other open campaign as a fallback. Each group is ordered by edition
   start date (soonest first, undated last), then slug.
4. The first ``CROSS_SELL_MAX_SUGGESTIONS`` are shown.

Registering for a suggestion copies the identity of the source
registration, so nobody re-enters their name or email.
"""

import datetime
from dataclasses import dataclass
from functools import partial
from urllib.parse import urlencode

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from course_management.observability import record_event
from courses.models.course import (
    CourseRegistration,
    Enrollment,
    RegistrationCampaign,
)

SOURCE_ONE_CLICK = "xsell"
SOURCE_LINK = "xsell-link"
SOURCE_EMAIL = "xsell-email"
LINK_SOURCES = {SOURCE_ONE_CLICK, SOURCE_LINK, SOURCE_EMAIL}

COPIED_FIELDS = (
    "email",
    "name",
    "company_name",
    "country",
    "region",
    "role",
    "years_experience",
    "accepted_newsletter",
)


@dataclass(frozen=True)
class Suggestion:
    campaign: RegistrationCampaign
    one_click: bool
    url: str

    @property
    def course(self):
        return self.campaign.current_course

    @property
    def start_date(self):
        course = self.course
        if course is None:
            return None
        return course.start_date


def suggestion_link_query(source_campaign, src=SOURCE_LINK) -> str:
    return urlencode({"src": src, "from": source_campaign.slug})


def campaign_requires_application(campaign) -> bool:
    course = campaign.current_course
    if course is None:
        return False
    return bool(course.requires_registration_approval)


def _sort_key(campaign):
    course = campaign.current_course
    start_date = course.start_date if course is not None else None
    return (
        start_date is None,
        start_date or datetime.date.max,
        campaign.slug,
    )


def _candidate_campaigns(source_campaign):
    excluded_slugs = list(settings.CROSS_SELL_EXCLUDED_CAMPAIGNS)
    excluded_slugs.append(source_campaign.slug)
    candidates = (
        RegistrationCampaign.objects.filter(
            is_active=True,
            exclude_from_suggestions=False,
        )
        .filter(
            Q(current_course__isnull=True)
            | Q(current_course__finished=False)
        )
        .exclude(slug__in=excluded_slugs)
        .select_related("current_course")
    )
    if source_campaign.current_course_id:
        candidates = candidates.exclude(
            current_course_id=source_campaign.current_course_id
        )
    return list(candidates)


def _taken_campaign_ids(user, email_normalized) -> set[int]:
    identity = Q()
    if user is not None and getattr(user, "is_authenticated", False):
        identity |= Q(user=user)
        account_email = (user.email or "").strip().lower()
        if account_email:
            identity |= Q(email_normalized=account_email)
    if email_normalized:
        identity |= Q(email_normalized=email_normalized)
    if not identity:
        return set()
    registered = CourseRegistration.objects.filter(identity)
    return set(registered.values_list("campaign_id", flat=True))


def _enrolled_course_ids(user) -> set[int]:
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    enrollments = Enrollment.objects.filter(student=user)
    return set(enrollments.values_list("course_id", flat=True))


def suggestions(
    source_campaign,
    user=None,
    email="",
    limit=None,
) -> list[Suggestion]:
    if limit is None:
        limit = settings.CROSS_SELL_MAX_SUGGESTIONS
    if limit <= 0:
        return []

    email_normalized = (email or "").strip().lower()
    taken = _taken_campaign_ids(user, email_normalized)
    enrolled = _enrolled_course_ids(user)
    candidates = [
        campaign
        for campaign in _candidate_campaigns(source_campaign)
        if campaign.pk not in taken
        and campaign.current_course_id not in enrolled
    ]

    curated_ids = set(
        source_campaign.suggested_campaigns.values_list("pk", flat=True)
    )
    curated = [c for c in candidates if c.pk in curated_ids]
    fallback = [c for c in candidates if c.pk not in curated_ids]
    ordered = sorted(curated, key=_sort_key) + sorted(fallback, key=_sort_key)

    query = suggestion_link_query(source_campaign)
    result = []
    for campaign in ordered[:limit]:
        url = reverse(
            "registration_campaign",
            kwargs={"campaign_slug": campaign.slug},
        )
        result.append(
            Suggestion(
                campaign=campaign,
                one_click=not campaign_requires_application(campaign),
                url=f"{url}?{query}",
            )
        )
    return result


def suggestions_for_registration(registration, limit=None):
    return suggestions(
        registration.campaign,
        user=registration.user,
        email=registration.email_normalized,
        limit=limit,
    )


def _copy_registration(source, campaign, now):
    registration = CourseRegistration(
        campaign=campaign,
        user=source.user,
        source=SOURCE_ONE_CLICK,
        referred_by=source,
    )
    for field_name in COPIED_FIELDS:
        setattr(registration, field_name, getattr(source, field_name))
    if source.email_confirmed:
        # Same address, already proven by the source registration.
        registration.email_confirmed = True
        registration.email_confirmation_confirmed_at = now
    return registration


def register_suggested(source, campaign_slugs, request=None):
    """Create registrations for the chosen one-click suggestions.

    Slugs outside the current suggestion set are ignored, so a stale or
    tampered form cannot register for arbitrary campaigns. Unconfirmed
    copies get no email of their own: confirming the source confirms
    them (see ``confirm_cross_sell_registrations``).
    """
    from course_management.relay.registration import (
        sync_registration_to_relay,
    )

    allowed = {
        suggestion.campaign.slug: suggestion.campaign
        for suggestion in suggestions_for_registration(source)
        if suggestion.one_click
    }
    now = timezone.now()
    created = []
    for slug in dict.fromkeys(campaign_slugs):
        campaign = allowed.get(slug)
        if campaign is None:
            continue
        registration = _copy_registration(source, campaign, now)
        try:
            with transaction.atomic():
                registration.save()
        except IntegrityError:
            # Double submit: the unique campaign+email row already exists.
            continue
        transaction.on_commit(
            partial(sync_registration_to_relay, registration)
        )
        record_event(
            "cross_sell.registered",
            request=request,
            user=getattr(request, "user", None),
            properties={
                "from_campaign_slug": source.campaign.slug,
                "campaign_slug": campaign.slug,
                "registration_id": registration.id,
                "referred_by_id": source.id,
                "source": SOURCE_ONE_CLICK,
            },
        )
        created.append(registration)
    return created


def confirm_cross_sell_registrations(registration, now=None):
    """Confirm the unconfirmed copies made from a just-confirmed source."""
    now = now or timezone.now()
    return CourseRegistration.objects.filter(
        referred_by=registration,
        email_normalized=registration.email_normalized,
        email_confirmed=False,
    ).update(
        email_confirmed=True,
        email_confirmation_confirmed_at=now,
    )


def remember_link_click(request, campaign) -> None:
    """Track a visit that came from a suggestion link (page or email)."""
    src = request.GET.get("src", "")
    if src not in LINK_SOURCES:
        return
    from_slug = request.GET.get("from", "")[:50]
    source = SOURCE_EMAIL if src == SOURCE_EMAIL else SOURCE_LINK
    clicks = request.session.get("cross_sell_clicks", {})
    clicks[str(campaign.pk)] = {"source": source, "from": from_slug}
    request.session["cross_sell_clicks"] = clicks
    record_event(
        "cross_sell.click",
        request=request,
        user=request.user,
        properties={
            "from_campaign_slug": from_slug,
            "campaign_slug": campaign.slug,
            "source": source,
        },
    )


def attribute_link_registration(request, registration) -> None:
    """Stamp source/referred_by on a form registration from a link click."""
    clicks = request.session.get("cross_sell_clicks", {})
    click = clicks.pop(str(registration.campaign_id), None)
    if click is None:
        return
    request.session["cross_sell_clicks"] = clicks
    registration.source = click["source"]
    registration.referred_by = CourseRegistration.objects.filter(
        campaign__slug=click["from"],
        email_normalized=registration.email_normalized,
    ).first()
    registration.save(update_fields=["source", "referred_by"])
    record_event(
        "cross_sell.registered",
        request=request,
        user=request.user,
        properties={
            "from_campaign_slug": click["from"],
            "campaign_slug": registration.campaign.slug,
            "registration_id": registration.id,
            "referred_by_id": registration.referred_by_id,
            "source": registration.source,
        },
    )


def record_impression(request, source_campaign, shown) -> None:
    if not shown:
        return
    record_event(
        "cross_sell.impression",
        request=request,
        user=request.user,
        properties={
            "from_campaign_slug": source_campaign.slug,
            "suggested_campaign_slugs": [
                suggestion.campaign.slug for suggestion in shown
            ],
        },
    )
