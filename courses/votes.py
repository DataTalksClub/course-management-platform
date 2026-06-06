from django.db.models import Count

from courses.models import ProjectVote


PROJECT_VOTES_PER_PROJECT = 3


def update_project_vote(user, submission, action="vote") -> None:
    if action == "remove":
        ProjectVote.objects.filter(
            voter=user,
            submission=submission,
        ).delete()
        return

    if ProjectVote.objects.filter(
        voter=user,
        submission=submission,
    ).exists():
        return

    vote_count = ProjectVote.objects.filter(
        voter=user,
        submission__project=submission.project,
    ).count()
    if vote_count >= PROJECT_VOTES_PER_PROJECT:
        return

    ProjectVote.objects.get_or_create(
        voter=user,
        submission=submission,
    )


def get_voted_submission_ids(user, course) -> set[int]:
    if not user.is_authenticated:
        return set()

    return set(
        ProjectVote.objects.filter(
            voter=user,
            submission__project__course=course,
        ).values_list("submission_id", flat=True)
    )


def get_project_vote_counts(user, course) -> dict[int, int]:
    if not user.is_authenticated:
        return {}

    return {
        row["submission__project_id"]: row["count"]
        for row in ProjectVote.objects.filter(
            voter=user,
            submission__project__course=course,
        )
        .values("submission__project_id")
        .annotate(count=Count("id"))
    }
