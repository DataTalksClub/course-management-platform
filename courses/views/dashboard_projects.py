from courses.models.project import ProjectSubmission
from courses.views.dashboard_metrics import safe_quartiles


def dashboard_project_stats(course, total_enrollments):
    project_submissions = dashboard_project_submission_rows(course)
    completion_rate = project_completion_rate(
        project_submissions,
        total_enrollments,
    )
    time_spent = project_submission_values(
        project_submissions,
        "time_spent",
    )
    scores = project_submission_values(project_submissions, "total_score")
    pass_count, fail_count = project_pass_fail_counts(project_submissions)
    time_quartiles = safe_quartiles(time_spent)
    score_quartiles = safe_quartiles(scores)
    rounded_completion_rate = round(completion_rate, 1)

    return {
        "project_completion_rate": rounded_completion_rate,
        "project_time_q25": time_quartiles.q25,
        "project_time_median": time_quartiles.median,
        "project_time_q75": time_quartiles.q75,
        "project_score_q25": score_quartiles.q25,
        "project_score_median": score_quartiles.median,
        "project_score_q75": score_quartiles.q75,
        "project_pass_count": pass_count,
        "project_fail_count": fail_count,
        "project_total_submissions": pass_count + fail_count,
    }


def dashboard_project_submission_rows(course):
    submission_rows = (
        ProjectSubmission.objects.filter(project__course=course)
        .select_related("project", "enrollment")
        .values("enrollment_id", "time_spent", "total_score", "passed")
    )
    return list(submission_rows)


def project_completion_rate(project_submissions, total_enrollments):
    if total_enrollments <= 0:
        return 0

    enrollment_ids = project_submission_enrollment_ids(project_submissions)
    completed_enrollments_count = len(enrollment_ids)
    return completed_enrollments_count / total_enrollments * 100


def project_submission_enrollment_ids(project_submissions):
    enrollment_ids = set()
    for submission in project_submissions:
        enrollment_ids.add(submission["enrollment_id"])
    return enrollment_ids


def project_submission_values(project_submissions, field_name):
    values = []
    for submission in project_submissions:
        value = submission[field_name]
        if value is not None:
            values.append(value)
    return values


def project_pass_fail_counts(project_submissions):
    pass_count = 0
    for submission in project_submissions:
        if submission["passed"]:
            pass_count += 1
    fail_count = len(project_submissions) - pass_count
    return pass_count, fail_count
