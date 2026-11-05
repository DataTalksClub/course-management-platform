def datetime_to_iso(value):
    if value is None:
        return None
    return value.isoformat()


def campaign_to_dict(campaign):
    current_course = campaign.current_course
    current_course_slug = None
    if current_course:
        current_course_slug = current_course.slug
    return {
        "slug": campaign.slug,
        "title": campaign.title,
        "edition_label": campaign.edition_label,
        "current_course": current_course_slug,
        "is_active": campaign.is_active,
        "marketing_markdown": campaign.marketing_markdown,
        "meta_description": campaign.meta_description,
        "hero_image_url": campaign.hero_image_url,
        "video_url": campaign.video_url,
    }


def registration_to_dict(registration):
    course = registration.course
    course_slug = None
    if course:
        course_slug = course.slug
    role_display = registration.get_role_display()
    created_at = datetime_to_iso(registration.created_at)
    return {
        "id": registration.id,
        "email": registration.email_normalized,
        "name": registration.name,
        "company_name": registration.company_name,
        "campaign": registration.campaign.slug,
        "course": course_slug,
        "country": registration.country,
        "region": registration.region,
        "role": registration.role,
        "role_display": role_display,
        "comment": registration.comment,
        "created_at": created_at,
    }
