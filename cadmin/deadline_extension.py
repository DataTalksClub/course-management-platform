from dataclasses import dataclass
from datetime import timedelta

from django.contrib import messages

from courses.models.project import ProjectState
from cadmin.views.helpers import redirect_after_action


@dataclass(frozen=True)
class ExtensionOption:
    days: int
    label: str


# Single source of truth for the "Extend deadline" choices offered in
# cadmin. Used both by the views (to validate the requested extension)
# and by the template (to render the dropdown).
EXTENSION_OPTIONS = (
    ExtensionOption(days=1, label="1 day"),
    ExtensionOption(days=3, label="3 days"),
    ExtensionOption(days=7, label="1 week"),
)

ALLOWED_EXTENSION_DAYS = {option.days for option in EXTENSION_OPTIONS}


def _extension_label(days):
    for option in EXTENSION_OPTIONS:
        if option.days == days:
            return option.label
    return f"{days} days"


def project_extension_plan(project):
    """Describe how to extend a project's deadlines for its current state.

    Returns ``(date_fields, deadline_label)`` or ``(None, None)`` when the
    state makes an extension irrelevant. While collecting submissions both
    deadlines move together so their spacing is preserved; during peer
    review the submission window has closed, so only the peer review
    deadline is left to move. Closed and completed projects offer nothing
    to extend.
    """
    if project.state == ProjectState.COLLECTING_SUBMISSIONS.value:
        return (
            ["submission_due_date", "peer_review_due_date"],
            "both deadlines",
        )
    if project.state == ProjectState.PEER_REVIEWING.value:
        return (["peer_review_due_date"], "the peer review deadline")
    return (None, None)


def parse_extension_days(request):
    """Return the requested extension in days, or None if it is invalid."""
    raw_days = request.POST.get("days")
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        return None
    if days not in ALLOWED_EXTENSION_DAYS:
        return None
    return days


def extend_deadlines(request, obj, date_fields, target_label, course_slug):
    """Push the given date fields on obj forward and redirect back.

    Shared by the homework and project deadline-extension views. Homework
    passes a single field; projects pass both the submission and peer
    review deadlines so a single action moves them together.
    """
    days = parse_extension_days(request)
    if days is None:
        messages.warning(request, "Invalid deadline extension.")
        return redirect_after_action(
            request, "cadmin_course", course_slug=course_slug
        )

    delta = timedelta(days=days)
    for field in date_fields:
        current_value = getattr(obj, field)
        setattr(obj, field, current_value + delta)
    obj.save(update_fields=list(date_fields))

    extension_label = _extension_label(days)
    messages.success(
        request,
        f"Extended {target_label} by {extension_label}.",
    )
    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )
