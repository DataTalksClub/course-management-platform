from django.db.models import Case, IntegerField, Value, When

from courses.models import (
    HomeworkState,
    ProjectSubmission,
    Submission,
)


def leaderboard_score_breakdown_context(enrollment, user):
    is_own_record = (
        user.is_authenticated and user.id == enrollment.student_id
    )
    public_profile = None
    if enrollment.display_public_profile:
        public_profile = enrollment.student
    show_public_profile_settings_link = (
        is_own_record and public_profile is None
    )
    submissions = leaderboard_homework_submissions(enrollment)
    project_submissions = leaderboard_project_submissions(enrollment)

    return {
        "enrollment": enrollment,
        "public_profile": public_profile,
        "show_public_profile_settings_link": show_public_profile_settings_link,
        "submissions": submissions,
        "project_submissions": project_submissions,
    }


def leaderboard_homework_submissions(enrollment):
    submissions = Submission.objects.filter(enrollment=enrollment)
    state_order = leaderboard_homework_state_order()
    return submissions.order_by(state_order, "homework__id")


def leaderboard_project_submissions(enrollment):
    return ProjectSubmission.objects.filter(
        enrollment=enrollment,
        volunteer_review_only=False,
    ).order_by("project__id")


def leaderboard_homework_state_order():
    scored_homework = Value(0)
    open_homework = Value(1)
    closed_homework = Value(2)
    other_homework = Value(3)
    scored_state = When(
        homework__state=HomeworkState.SCORED.value,
        then=scored_homework,
    )
    open_state = When(
        homework__state=HomeworkState.OPEN.value,
        then=open_homework,
    )
    closed_state = When(
        homework__state=HomeworkState.CLOSED.value,
        then=closed_homework,
    )
    output_field = IntegerField()
    return Case(
        scored_state,
        open_state,
        closed_state,
        default=other_homework,
        output_field=output_field,
    )
