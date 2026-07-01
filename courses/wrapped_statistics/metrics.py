from operator import attrgetter, itemgetter

from courses.models.wrapped import UserWrappedStatistics

from .types import (
    UserWrappedMetrics,
    UserWrappedStatData,
    WrappedLeaderboardUserScore,
)


def wrapped_course_stats(enrollments, courses):
    """Per-course enrollment counts, sorted most-popular first."""
    course_stats_list = []
    for course in courses:
        enrollment_count = enrollments.filter(course=course).count()
        course_stats = {
            "title": course.title,
            "slug": course.slug,
            "enrollment_count": enrollment_count,
        }
        course_stats_list.append(course_stats)
    enrollment_count_key = itemgetter("enrollment_count")
    course_stats_list.sort(key=enrollment_count_key, reverse=True)
    return course_stats_list


def wrapped_leaderboard(enrollments):
    """Top-100 leaderboard, summing each student's score across courses."""
    user_scores = wrapped_leaderboard_scores(enrollments)
    top_scores = top_wrapped_leaderboard_scores(user_scores)
    return wrapped_leaderboard_entries(top_scores)


def wrapped_leaderboard_scores(enrollments):
    user_scores_by_student_id = {}
    for enrollment in enrollments:
        user_score = user_scores_by_student_id.get(enrollment.student_id)
        if user_score is None:
            user_score = WrappedLeaderboardUserScore(
                student=enrollment.student,
                display_name=enrollment.display_name,
            )
            user_scores_by_student_id[enrollment.student_id] = user_score

        user_score.total_score += enrollment.total_score or 0

    return user_scores_by_student_id


def top_wrapped_leaderboard_scores(user_scores):
    user_score_values = user_scores.values()
    total_score_key = attrgetter("total_score")
    sorted_scores = sorted(
        user_score_values,
        key=total_score_key,
        reverse=True,
    )
    return sorted_scores[:100]


def wrapped_leaderboard_entries(user_scores):
    leaderboard = []
    for rank, user_score in enumerate(user_scores, start=1):
        leaderboard_entry = {
            "rank": rank,
            "display_name": user_score.display_name,
            "total_score": user_score.total_score,
            "student_id": user_score.student.id,
        }
        leaderboard.append(leaderboard_entry)
    return leaderboard


def has_faq_contribution(submission):
    if not submission.faq_contribution_url:
        return False
    stripped_url = submission.faq_contribution_url.strip()
    if stripped_url:
        return True
    return False


def wrapped_courses(enrollments):
    courses = []
    for enrollment in enrollments:
        course_record = {
            "title": enrollment.course.title,
            "score": enrollment.total_score,
            "slug": enrollment.course.slug,
            "enrollment_id": enrollment.id,
        }
        courses.append(course_record)
    return courses


def wrapped_certificates_count(enrollments):
    count = 0
    for enrollment in enrollments:
        if enrollment.certificate_url and enrollment.certificate_url.strip():
            count += 1
    return count


def capped_hours(value):
    if value:
        hours = value
    else:
        hours = 0
    capped_hours = min(hours, 100.0)
    return capped_hours


def wrapped_homework_hours(submission):
    lecture_hours = capped_hours(submission.time_spent_lectures)
    homework_hours = capped_hours(submission.time_spent_homework)
    return lecture_hours + homework_hours


def wrapped_total_hours(homework_submissions, project_submissions):
    homework_hours = 0
    for submission in homework_submissions:
        homework_hours += wrapped_homework_hours(submission)

    project_hours = 0
    for submission in project_submissions:
        time_spent = submission.time_spent
        project_hours += capped_hours(time_spent)

    return round(homework_hours + project_hours, 1)


def wrapped_learning_in_public_count(
    homework_submissions,
    project_submissions,
):
    homework_links = 0
    for homework_submission in homework_submissions:
        if homework_submission.learning_in_public_links:
            homework_links += len(homework_submission.learning_in_public_links)

    project_links = 0
    for project_submission in project_submissions:
        if project_submission.learning_in_public_links:
            project_links += len(project_submission.learning_in_public_links)

    return homework_links + project_links


def wrapped_faq_count(homework_submissions, project_submissions):
    count = 0
    for submission in homework_submissions:
        if has_faq_contribution(submission):
            count += 1
    for submission in project_submissions:
        if has_faq_contribution(submission):
            count += 1
    return count


def wrapped_rank(student, leaderboard_data):
    for entry in leaderboard_data:
        if entry["student_id"] == student.id:
            return entry["rank"]
    return None


def wrapped_total_points(enrollments):
    total_points = 0
    for enrollment in enrollments:
        total_points += enrollment.total_score or 0
    return total_points


def wrapped_display_name(student, enrollments):
    if enrollments:
        return enrollments[0].display_name
    return student.username


def user_wrapped_metrics_values(data: UserWrappedStatData):
    total_points = wrapped_total_points(data.enrollments)
    total_hours = wrapped_total_hours(
        data.homework_submissions,
        data.project_submissions,
    )
    learning_in_public_count = wrapped_learning_in_public_count(
        data.homework_submissions,
        data.project_submissions,
    )
    faq_contributions_count = wrapped_faq_count(
        data.homework_submissions,
        data.project_submissions,
    )
    certificates_earned = wrapped_certificates_count(data.enrollments)
    courses = wrapped_courses(data.enrollments)
    rank = wrapped_rank(data.student, data.leaderboard_data)
    display_name = wrapped_display_name(data.student, data.enrollments)

    values = {
        "total_points": total_points,
        "total_hours": total_hours,
        "learning_in_public_count": learning_in_public_count,
        "faq_contributions_count": faq_contributions_count,
        "certificates_earned": certificates_earned,
        "courses": courses,
        "rank": rank,
        "display_name": display_name,
    }
    return values


def user_wrapped_statistics_values(data, metrics, homework_count, project_count):
    values = {
        "wrapped": data.stats,
        "user": data.student,
        "total_points": metrics.total_points,
        "total_hours": metrics.total_hours,
        "homework_count": homework_count,
        "project_count": project_count,
        "peer_reviews_given": data.peer_reviews_count,
        "learning_in_public_count": metrics.learning_in_public_count,
        "faq_contributions_count": metrics.faq_contributions_count,
        "certificates_earned": metrics.certificates_earned,
        "courses": metrics.courses,
        "rank": metrics.rank,
        "display_name": metrics.display_name,
    }
    return values


def build_user_wrapped_stat(data: UserWrappedStatData):
    """Build an (unsaved) UserWrappedStatistics row for one student."""
    metric_values = user_wrapped_metrics_values(data)
    metrics = UserWrappedMetrics(**metric_values)
    homework_count = len(data.homework_submissions)
    project_count = len(data.project_submissions)
    values = user_wrapped_statistics_values(
        data,
        metrics,
        homework_count,
        project_count,
    )
    user_stat = UserWrappedStatistics(**values)
    return user_stat
