from .urls import public_route_url


def score_notification_urls(course, assignment, route_name, slug_kwarg):
    assignment_kwargs = {
        "course_slug": course.slug,
        slug_kwarg: assignment.slug,
    }
    assignment_url = public_route_url(route_name, assignment_kwargs)

    course_kwargs = {"course_slug": course.slug}
    course_url = public_route_url("course", course_kwargs)
    leaderboard_url = public_route_url("leaderboard", course_kwargs)
    profile_url = public_route_url("account_settings")

    return {
        "course_url": course_url,
        "assignment_url": assignment_url,
        "leaderboard_url": leaderboard_url,
        "profile_url": profile_url,
    }


def score_notification_footer(course, assignment, profile_url):
    return {
        "notification_footer": (
            f"You are receiving this because you submitted {assignment.title} "
            f"for {course.title} and homework/project submission emails "
            "are enabled in your profile."
        ),
        "notification_footer_text": (
            "If you don't want to receive homework/project submission "
            "and score emails, turn off homework and project submission "
            f"emails in your profile: {profile_url}"
        ),
    }


def add_from_email_if_configured(payload, config):
    if config.from_email:
        payload["from_email"] = config.from_email
    return payload
