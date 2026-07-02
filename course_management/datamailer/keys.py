import re

from django.utils.text import slugify


def course_family_slug(course) -> str:
    slug = course.slug
    without_year = re.sub(r"[-_ ]?\d{4}$", "", slug)
    family_slug = without_year.strip("-_ ")
    if family_slug:
        return family_slug
    return slug


def contact_tags_for_course(course) -> list[str]:
    family_slug = course_family_slug(course)
    return [
        f"course-{family_slug}",
        f"course-cohort-{course.slug}",
    ]


def registration_list_key(registration) -> str:
    if registration.course_id:
        return registration.course.slug
    return registration.campaign.slug


def course_enrolled_list_key(course) -> str:
    return f"{course.slug}:@e"


def homework_submitters_list_key(homework) -> str:
    return f"{homework.course.slug}:@e:@homework:{homework.slug}"


def project_submitters_list_key(project) -> str:
    return f"{project.course.slug}:@e:@project:{project.slug}"


def project_passed_list_key(project) -> str:
    return f"{project_submitters_list_key(project)}:@passed"


def course_graduates_list_key(course) -> str:
    return f"{course.slug}:@e:@graduated"


def registration_campaign_external_key(campaign) -> str:
    return f"cmp-registration-{slugify(campaign.slug)}"


def _object_user_ordering_key(obj) -> str:
    student_id = getattr(obj, "student_id", None)
    if student_id:
        return f"user:{student_id}"

    user_id = getattr(obj, "user_id", None)
    if user_id:
        return f"user:{user_id}"

    return ""


def _object_email_ordering_key(obj) -> str:
    email = (
        getattr(obj, "email_normalized", "")
        or getattr(obj, "email", "")
        or ""
    ).strip().lower()
    if email:
        return f"email:{email}"

    return ""


def datamailer_ordering_key(obj) -> str:
    user_key = _object_user_ordering_key(obj)
    if user_key:
        return user_key

    email_key = _object_email_ordering_key(obj)
    if email_key:
        return email_key

    return f"{obj.__class__.__name__}:{obj.pk}"
