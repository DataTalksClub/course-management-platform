"""One row per invitee whose approval earned referral bonus points.

The one-to-one on the referred registration makes the award
idempotent: repeated approvals never pay twice.
"""

from django.db import models


class ReferralReward(models.Model):
    referred = models.OneToOneField(
        "courses.CourseRegistration",
        on_delete=models.CASCADE,
        related_name="referral_reward",
        help_text="Invitee registration whose approval earned the bonus.",
    )
    referrer = models.ForeignKey(
        "courses.CourseRegistration",
        on_delete=models.CASCADE,
        related_name="referral_rewards_earned",
        help_text="Registration that invited the referred applicant.",
    )
    points = models.PositiveIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"+{self.points} referral points for "
            f"{self.referrer_id} (invitee {self.referred_id})"
        )
