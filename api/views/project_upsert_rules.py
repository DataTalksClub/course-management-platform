from courses.models.project import ProjectState

from api.safety import PatchFieldRules


PROJECT_PATCH_FIELDS = {
    "title",
    "description",
    "submission_due_date",
    "peer_review_due_date",
    "instructions_url",
    "state",
    "learning_in_public_cap_project",
    "learning_in_public_cap_review",
    "number_of_peers_to_evaluate",
    "points_for_peer_review",
    "time_spent_project_field",
    "problems_comments_field",
    "faq_contribution_field",
}

VALID_PROJECT_STATES = set()
for project_state in ProjectState:
    VALID_PROJECT_STATES.add(project_state.value)

PROJECT_PATCH_RULES = PatchFieldRules(
    PROJECT_PATCH_FIELDS,
    VALID_PROJECT_STATES,
    "invalid_project_state",
    {"submission_due_date", "peer_review_due_date"},
)

PROJECT_UPSERT_REQUIRED_DATES = (
    "submission_due_date",
    "peer_review_due_date",
)
