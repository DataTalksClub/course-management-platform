from courses.models.project import ProjectState


def project_delete_blockers(project, submissions_count):
    blockers = []
    if project.state != ProjectState.CLOSED.value:
        blockers.append("not_closed")
    if submissions_count > 0:
        blockers.append("has_submissions")
    return blockers


def project_deadline_fields(project):
    submission_due_date = project.submission_due_date.isoformat()
    peer_review_due_date = project.peer_review_due_date.isoformat()
    return {
        "submission_due_date": submission_due_date,
        "peer_review_due_date": peer_review_due_date,
    }


def project_identity_fields(project):
    return {
        "id": project.id,
        "slug": project.slug,
        "title": project.title,
        "description": project.description,
        "instructions_url": project.instructions_url,
        "state": project.state,
    }


def project_settings_fields(project):
    return {
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
    }


def project_deletion_fields(project):
    submissions_count = project.projectsubmission_set.count()
    delete_blockers = project_delete_blockers(project, submissions_count)
    return {
        "submissions_count": submissions_count,
        "can_delete": not delete_blockers,
        "delete_blockers": delete_blockers,
    }


def project_to_dict(project):
    identity_fields = project_identity_fields(project)
    settings_fields = project_settings_fields(project)
    deadline_fields = project_deadline_fields(project)
    deletion_fields = project_deletion_fields(project)
    result = {
        **identity_fields,
        **settings_fields,
        **deadline_fields,
        **deletion_fields,
    }
    return result
