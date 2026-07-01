from courses.models.project import ProjectState


def project_delete_blockers(project):
    blockers = []
    submissions_count = project.projectsubmission_set.count()
    if project.state != ProjectState.CLOSED.value:
        blockers.append("not_closed")
    if submissions_count > 0:
        blockers.append("has_submissions")
    return blockers


def project_to_dict(project):
    submissions_count = project.projectsubmission_set.count()
    delete_blockers = project_delete_blockers(project)
    return {
        "id": project.id,
        "slug": project.slug,
        "title": project.title,
        "description": project.description,
        "instructions_url": project.instructions_url,
        "submission_due_date": project.submission_due_date.isoformat(),
        "peer_review_due_date": project.peer_review_due_date.isoformat(),
        "state": project.state,
        "learning_in_public_cap_project": (
            project.learning_in_public_cap_project
        ),
        "learning_in_public_cap_review": (
            project.learning_in_public_cap_review
        ),
        "number_of_peers_to_evaluate": (
            project.number_of_peers_to_evaluate
        ),
        "points_for_peer_review": project.points_for_peer_review,
        "time_spent_project_field": project.time_spent_project_field,
        "problems_comments_field": project.problems_comments_field,
        "faq_contribution_field": project.faq_contribution_field,
        "submissions_count": submissions_count,
        "can_delete": not delete_blockers,
        "delete_blockers": delete_blockers,
    }
