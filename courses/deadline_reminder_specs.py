from courses.deadline_reminder_types import ReminderSpec


HOMEWORK_REMINDER_SPEC_VALUES = {
    "deadline_kind": "homework",
    "event_kind": "homework",
    "list_kind": "homework",
    "item_type": "homework",
    "route_name": "homework",
    "route_slug_kwarg": "homework_slug",
    "metadata_slug_key": "homework_slug",
    "metadata_id_key": "homework_id",
    "list_name_suffix": "deadline reminders",
}


PROJECT_SUBMISSION_REMINDER_SPEC_VALUES = {
    "deadline_kind": "project_submission",
    "event_kind": "project",
    "list_kind": "project-submission",
    "item_type": "project",
    "route_name": "project",
    "route_slug_kwarg": "project_slug",
    "metadata_slug_key": "project_slug",
    "metadata_id_key": "project_id",
    "list_name_suffix": "submission deadline reminders",
}


PEER_REVIEW_REMINDER_SPEC_VALUES = {
    "deadline_kind": "peer_review",
    "event_kind": "peer-review",
    "list_kind": "peer-review",
    "item_type": "peer_review",
    "route_name": "projects_eval",
    "route_slug_kwarg": "project_slug",
    "metadata_slug_key": "project_slug",
    "metadata_id_key": "project_id",
    "list_name_suffix": "peer review deadline reminders",
}


HOMEWORK_REMINDER_SPEC = ReminderSpec(**HOMEWORK_REMINDER_SPEC_VALUES)
PROJECT_SUBMISSION_REMINDER_SPEC = ReminderSpec(
    **PROJECT_SUBMISSION_REMINDER_SPEC_VALUES
)
PEER_REVIEW_REMINDER_SPEC = ReminderSpec(**PEER_REVIEW_REMINDER_SPEC_VALUES)
