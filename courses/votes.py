from django.db.models import Count

from courses.models.project import ProjectVote


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

    votes = ProjectVote.objects.filter(
        voter=user,
        submission__project__course=course,
    )
    submission_ids = votes.values_list("submission_id", flat=True)
    return set(submission_ids)


def get_project_vote_counts(user, course) -> dict[int, int]:
    if not user.is_authenticated:
        return {}

    project_vote_counts = {}
    rows = (
        ProjectVote.objects.filter(
            voter=user,
            submission__project__course=course,
        )
        .values("submission__project_id")
        .annotate(count=Count("id"))
    )
    for row in rows:
        project_id = row["submission__project_id"]
        vote_count = row["count"]
        project_vote_counts[project_id] = vote_count
    return project_vote_counts
