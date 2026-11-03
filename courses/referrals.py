"""Referral program: invite links and acceptance bonus points.

An approved applicant gets a personal invite link
(``/register/<campaign>/?ref=<registration_id>``). An invitee who
registers with the inviter's email (prefilled from the link) gets
``referred_by`` stamped on their registration. When the invitee is
approved, the inviter's enrollment in that course earns
``REFERRAL_BONUS_POINTS`` — exactly once per invitee
(``ReferralReward`` is one-to-one on the referred registration).

Points live in ``Enrollment.bonus_points`` so the leaderboard
recompute (homework + project sums) preserves them.
"""

import logging

from django.db import transaction
from django.db.models import F
from django.urls import reverse

logger = logging.getLogger(__name__)

REFERRAL_BONUS_POINTS = 3


def invite_path_for_registration(registration) -> str:
    return (
        reverse(
            "registration_campaign",
            kwargs={"campaign_slug": registration.campaign.slug},
        )
        + f"?ref={registration.pk}"
    )


def invite_url_for_registration(registration, base_url: str) -> str:
    return base_url.rstrip("/") + invite_path_for_registration(registration)


def _referrer_user(referrer_registration):
    user = getattr(referrer_registration, "user", None)
    if user is not None:
        return user
    email = (
        getattr(referrer_registration, "email_normalized", "") or ""
    ).strip()
    if not email:
        return None
    from accounts.models import CustomUser

    return CustomUser.objects.filter(email__iexact=email).first()


def award_referral_bonus(registration):
    """Award bonus points for an approved referred registration.

    Idempotent: one ``ReferralReward`` per invitee. Returns the reward,
    or None when there is nothing to award (no referrer, self-referral,
    or the referrer has no user account to attach an enrollment to).
    """
    from courses.models import ReferralReward
    from courses.models.course import Enrollment

    referrer_id = getattr(registration, "referred_by_id", None)
    if not referrer_id or referrer_id == registration.pk:
        return None
    referrer = registration.referred_by
    if referrer is None or registration.course_id is None:
        return None
    user = _referrer_user(referrer)
    if user is None:
        logger.info(
            "Referral bonus skipped: no user account for referrer "
            "registration_id=%s",
            referrer.pk,
        )
        return None
    with transaction.atomic():
        reward, created = ReferralReward.objects.get_or_create(
            referred=registration,
            defaults={
                "referrer_id": referrer.pk,
                "points": REFERRAL_BONUS_POINTS,
            },
        )
        if not created:
            return reward
        enrollment, _ = Enrollment.objects.get_or_create(
            student=user,
            course_id=registration.course_id,
        )
        Enrollment.objects.filter(pk=enrollment.pk).update(
            bonus_points=F("bonus_points") + reward.points
        )
    return reward
