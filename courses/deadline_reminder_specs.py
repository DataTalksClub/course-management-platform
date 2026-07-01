from courses.deadline_reminder_types import ReminderSpec


def homework_reminder_spec():
    return ReminderSpec(
        deadline_kind="homework",
        event_kind="homework",
        list_kind="homework",
        item_type="homework",
        route_name="homework",
        route_slug_kwarg="homework_slug",
        metadata_slug_key="homework_slug",
        metadata_id_key="homework_id",
        list_name_suffix="deadline reminders",
    )


def project_submission_reminder_spec():
    return ReminderSpec(
        deadline_kind="project_submission",
        event_kind="project",
        list_kind="project-submission",
        item_type="project",
        route_name="project",
        route_slug_kwarg="project_slug",
        metadata_slug_key="project_slug",
        metadata_id_key="project_id",
        list_name_suffix="submission deadline reminders",
    )


def peer_review_reminder_spec():
    return ReminderSpec(
        deadline_kind="peer_review",
        event_kind="peer-review",
        list_kind="peer-review",
        item_type="peer_review",
        route_name="projects_eval",
        route_slug_kwarg="project_slug",
        metadata_slug_key="project_slug",
        metadata_id_key="project_id",
        list_name_suffix="peer review deadline reminders",
    )
