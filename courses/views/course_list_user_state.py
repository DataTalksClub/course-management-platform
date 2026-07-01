from courses.models.course import (
    CourseRegistration,
    Enrollment,
    RegistrationCampaign,
)


def attach_registration_campaigns(courses) -> None:
    course_ids = []
    for course in courses:
        course_ids.append(course.id)
    campaigns = RegistrationCampaign.objects.filter(
        current_course_id__in=course_ids,
        is_active=True,
    ).order_by("id")
    campaign_by_course_id = {}
    for campaign in campaigns:
        campaign_by_course_id.setdefault(campaign.current_course_id, campaign)

    for course in courses:
        course.registration_campaign = campaign_by_course_id.get(course.id)


def registration_campaign_ids(courses):
    campaign_ids = []
    for course in courses:
        registration_campaign = getattr(course, "registration_campaign", None)
        if registration_campaign:
            campaign_ids.append(registration_campaign.id)
    return campaign_ids


def normalized_user_email(user) -> str:
    email = user.email or ""
    stripped_email = email.strip()
    return stripped_email.lower()


def registered_campaign_ids(campaign_ids, user):
    email_normalized = normalized_user_email(user)
    registration_ids = CourseRegistration.objects.filter(
        campaign_id__in=campaign_ids,
        email_normalized=email_normalized,
    ).values_list("campaign_id", flat=True)
    return set(registration_ids)


def mark_registered_course(course, registered_campaign_ids) -> None:
    campaign = getattr(course, "registration_campaign", None)
    course.is_registered = (
        campaign is not None and campaign.id in registered_campaign_ids
    )


def mark_registered_courses(courses, user) -> None:
    if not user.is_authenticated:
        return

    campaign_ids = registration_campaign_ids(courses)
    registered_ids = registered_campaign_ids(campaign_ids, user)
    for course in courses:
        mark_registered_course(course, registered_ids)


def mark_enrolled_courses(courses, user) -> None:
    if not user.is_authenticated:
        return

    course_ids = []
    for course in courses:
        course_ids.append(course.id)
    enrolled_ids = Enrollment.objects.filter(
        student=user,
        course_id__in=course_ids,
    ).values_list("course_id", flat=True)
    enrolled_course_ids = set(enrolled_ids)

    for course in courses:
        course.is_enrolled = course.id in enrolled_course_ids
