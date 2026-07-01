from courses.models import CourseRegistration

from .helpers import count_by


def registration_campaign_metrics(campaign):
    registrations = CourseRegistration.objects.filter(campaign=campaign)
    total = registrations.count()
    by_role = count_by(registrations, "role")
    by_country = count_by(registrations, "country")
    by_region = count_by(registrations, "region")
    return {
        "campaign": campaign,
        "total": total,
        "by_role": by_role,
        "by_country": by_country,
        "by_region": by_region,
    }
