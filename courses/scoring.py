import logging
import statistics

from time import time
from enum import Enum
from datetime import datetime
from collections import defaultdict

from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import Least

from django.db import transaction
from django.core.cache import cache


from .models import (
    Homework,
    HomeworkState,
    HomeworkStatistics,
    Submission,
    Question,
    Answer,
    Course,
    QuestionTypes,
    AnswerTypes,
    Enrollment,
    Project,
    ProjectSubmission,
    ProjectStatistics,
    ProjectState,
    PeerReview,
    WrappedStatistics,
    UserWrappedStatistics,
)


logger = logging.getLogger(__name__)


class HomeworkScoringStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


def is_float_equal(
    value1: str, value2: str, tolerance: float = 0.01
) -> bool:
    try:
        return abs(float(value1) - float(value2)) <= tolerance
    except ValueError:
        return False


def is_integer_equal(value1: str, value2: str) -> bool:
    try:
        return int(value1) == int(value2)
    except ValueError:
        return False


def safe_split(value: str, delimiter: str = ","):
    if not value:
        return []

    value = value.strip()
    return value.split(delimiter)


def safe_split_to_int(value: str, delimiter: str = ","):
    raw = safe_split(value, delimiter)
    return [int(x) for x in raw]


def is_multiple_choice_answer_correct(
    question: Question, answer: Answer
) -> bool:
    user_answer = answer.answer_text

    if not user_answer:
        return False

    selected_option = int(user_answer)
    correct_answer = question.get_correct_answer_indices()
    return selected_option in correct_answer


def is_checkbox_answer_correct(
    question: Question, answer: Answer
) -> bool:
    user_answer = answer.answer_text
    selected_options = set(safe_split_to_int(user_answer))
    correct_answer = question.get_correct_answer_indices()
    return selected_options == correct_answer


def is_free_form_answer_correct(
    question: Question, answer: Answer
) -> bool:
    answer_type = question.answer_type

    user_answer = answer.answer_text
    user_answer = (user_answer or "").strip()

    if answer_type == AnswerTypes.ANY.value:
        # For "ANY" type, require non-empty answer
        return len(user_answer) > 0

    user_answer_lower = user_answer.lower()

    correct_answer = question.get_correct_answer()
    correct_answer = (correct_answer or "").strip().lower()

    if answer_type == AnswerTypes.EXACT_STRING.value:
        return user_answer_lower == correct_answer
    elif answer_type == AnswerTypes.CONTAINS_STRING.value:
        return correct_answer in user_answer_lower
    elif answer_type == AnswerTypes.FLOAT.value:
        return is_float_equal(
            user_answer, correct_answer, tolerance=0.01
        )
    elif answer_type == AnswerTypes.INTEGER.value:
        return is_integer_equal(user_answer, correct_answer)

    return False


def is_answer_correct(question: Question, answer: Answer) -> bool:
    if question.answer_type == AnswerTypes.ANY.value:
        return True

    if question.question_type == QuestionTypes.MULTIPLE_CHOICE.value:
        return is_multiple_choice_answer_correct(question, answer)

    if question.question_type == QuestionTypes.CHECKBOXES.value:
        return is_checkbox_answer_correct(question, answer)

    if question.question_type == QuestionTypes.FREE_FORM.value:
        return is_free_form_answer_correct(question, answer)

    if question.question_type == QuestionTypes.FREE_FORM_LONG.value:
        return is_free_form_answer_correct(question, answer)

    return False


def update_learning_in_public_score(submission: Submission) -> int:
    learning_in_public_score = 0

    # Check if learning in public is disabled for this enrollment
    if submission.enrollment.disable_learning_in_public:
        submission.learning_in_public_score = 0
        return 0

    if submission.learning_in_public_links:
        learning_in_public_score = len(
            submission.learning_in_public_links
        )
        submission.learning_in_public_score = learning_in_public_score

    return learning_in_public_score


def update_faq_score(submission: Submission) -> int:
    faq_score = 0

    if (
        submission.faq_contribution_url
        and len(submission.faq_contribution_url) >= 5
    ):
        faq_score = 1
        submission.faq_score = faq_score

    return faq_score


def update_score(
    submission: Submission, answers: list[Answer], save: bool = True
) -> None:
    logger.info(f"Scoring submission {submission.id}")
    questions_score = 0

    for answer in answers:
        question = answer.question
        try:
            is_correct = is_answer_correct(question, answer)
        except Exception as e:
            logger.exception(
                f"Error while scoring submission {submission.id}"
            )
            raise e
            # is_correct = False

        answer.is_correct = is_correct
        if save:
            answer.save()

        if is_correct:
            questions_score += question.scores_for_correct_answer

    submission.questions_score = questions_score

    lip_score = update_learning_in_public_score(submission)
    faq_score = update_faq_score(submission)

    total_score = questions_score + lip_score + faq_score

    submission.total_score = total_score

    if save:
        submission.save()


def _homework_scoring_error(homework, homework_id):
    if homework.due_date > timezone.now():
        return (
            "The due date for "
            f"{homework_id} is in the future. Update the due date to score."
        )
    if homework.state == HomeworkState.CLOSED.value:
        return (
            f"Homework {homework_id} is closed. "
            "Update the state to OPEN to score."
        )
    if homework.state == HomeworkState.SCORED.value:
        return f"Homework {homework_id} is already scored."
    return None


def _answers_by_submission(answers):
    answers_by_submission_id = defaultdict(list)
    for answer in answers:
        answers_by_submission_id[answer.submission_id].append(answer)
    return answers_by_submission_id


def _score_homework_submission_batch(
    submissions,
    answers_by_submission_id,
):
    for submission in submissions:
        submission_answers = answers_by_submission_id[submission.id]
        update_score(submission, submission_answers, save=False)


def _persist_scored_homework_submissions(homework_id, submissions, answers):
    logger.info(f"Updating the submissions for homework {homework_id}")
    Submission.objects.bulk_update(
        submissions,
        [
            "questions_score",
            "learning_in_public_score",
            "faq_score",
            "total_score",
        ],
    )

    logger.info(f"Updating answers for homework {homework_id}")
    Answer.objects.bulk_update(answers, ["is_correct"])


def _homework_scoring_batch(homework_id):
    submissions = Submission.objects.filter(homework__id=homework_id)
    answers = Answer.objects.filter(
        submission__in=submissions
    ).select_related("question", "submission")
    answers_by_submission_id = _answers_by_submission(answers)
    return submissions, answers, answers_by_submission_id


def _mark_homework_scored(homework):
    homework.state = HomeworkState.SCORED.value
    homework.save()

    course = homework.course
    update_leaderboard(course)

    course.first_homework_scored = True
    course.save()

    calculate_homework_statistics(homework, force=True)


def _homework_scoring_success(homework_id, started_at):
    logger.info(f"Scored homework in {(time() - started_at):.2f} seconds")
    return (
        HomeworkScoringStatus.OK,
        f"Homework {homework_id} is scored",
    )


def score_homework_submissions(
    homework_id: str,
) -> tuple[HomeworkScoringStatus, str]:
    with transaction.atomic():
        t0 = time()
        logger.info(f"Scoring submissions for homework {homework_id}")

        homework = Homework.objects.get(pk=homework_id)

        if error := _homework_scoring_error(homework, homework_id):
            return (HomeworkScoringStatus.FAIL, error)

        submissions, answers, answers_by_submission_id = (
            _homework_scoring_batch(homework_id)
        )
        logger.info(
            f"Scoring {len(answers_by_submission_id)} submissions for homework {homework_id}"
        )

        _score_homework_submission_batch(
            submissions,
            answers_by_submission_id,
        )
        _persist_scored_homework_submissions(
            homework_id,
            submissions,
            answers,
        )

        logger.info(
            f"Scored {len(submissions)} submissions for homework {homework_id}"
        )
        _mark_homework_scored(homework)

        return _homework_scoring_success(homework_id, t0)


def _homework_scores_by_enrollment(course):
    homeworks = Homework.objects.filter(course=course)
    aggregated_homework_scores = (
        Submission.objects.filter(homework__in=homeworks)
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )
    return {
        score["enrollment"]: score["total_score"]
        for score in aggregated_homework_scores
    }


def _project_scores_by_enrollment(course):
    projects = Project.objects.filter(course=course)
    aggregated_project_scores = (
        ProjectSubmission.objects.filter(
            project__in=projects,
            volunteer_review_only=False,
        )
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )
    return {
        score["enrollment"]: score["total_score"]
        for score in aggregated_project_scores
    }


def _rank_enrollments(enrollments):
    enrollments = sorted(
        enrollments,
        key=lambda x: (-(x.total_score or 0), x.id),
    )
    for rank, enrollment in enumerate(enrollments, 1):
        enrollment.position_on_leaderboard = rank
    return enrollments


def _update_enrollment_totals(course):
    homework_scores = _homework_scores_by_enrollment(course)
    project_scores = _project_scores_by_enrollment(course)
    enrollments = list(Enrollment.objects.filter(course=course))

    for enrollment in enrollments:
        enrollment.total_score = (
            homework_scores.get(enrollment.id, 0)
            + project_scores.get(enrollment.id, 0)
        )

    enrollments = _rank_enrollments(enrollments)

    Enrollment.objects.bulk_update(
        enrollments,
        ["total_score", "position_on_leaderboard"],
    )


def _invalidate_leaderboard_caches(course):
    cache.delete(f"leaderboard:{course.id}")
    cache.delete(f"leaderboard_data:{course.id}")
    cache.delete(f"leaderboard_yaml:{course.id}")
    version_key = f"leaderboard_cache_version:{course.id}"
    cache.set(version_key, cache.get(version_key, 1) + 1, None)
    logger.info(f"Invalidated cache for leaderboard of course {course.id}")


def update_leaderboard(course: Course):
    t0 = time()
    logger.info(f"Updating leaderboard for course {course.id}")
    _update_enrollment_totals(course)
    _invalidate_leaderboard_caches(course)
    t1 = time()
    logger.info(f"Updated leaderboard in {(t1 - t0):.2f} seconds")


def fill_most_common_answer_as_correct(question: Question) -> None:
    if question.correct_answer and not has_invalid_correct_answer_indices(question):
        logger.info(f"Correct answer for {question} is already set")
        return

    most_common_answer = (
        Answer.objects.filter(
            question=question,
            answer_text__isnull=False,
            answer_text__gt="",
        )
        .values("answer_text")
        .annotate(count=Count("answer_text"))
        .order_by("-count")
        .first()
    )

    if not most_common_answer:
        logger.warning(f"No answers for {question}")
        return

    answer = most_common_answer["answer_text"]
    question.correct_answer = answer
    question.save()
    logger.info(f"Updated answer for {question} to {answer}")


def has_invalid_correct_answer_indices(question: Question) -> bool:
    if question.question_type not in [
        QuestionTypes.MULTIPLE_CHOICE.value,
        QuestionTypes.CHECKBOXES.value,
    ]:
        return False

    possible_answers = question.get_possible_answers()
    if not possible_answers:
        return False

    try:
        indices = question.get_correct_answer_indices()
    except ValueError:
        return True

    return any(index < 1 or index > len(possible_answers) for index in indices)


def fill_correct_answers(homework: Homework) -> None:
    questions = Question.objects.filter(homework=homework)

    for question in questions:
        fill_most_common_answer_as_correct(question)


def clear_correct_answers(homework: Homework) -> int:
    return Question.objects.filter(homework=homework).update(correct_answer="")


HOMEWORK_STAT_FIELDS = [
    "questions_score",
    "learning_in_public_score",
    "total_score",
    "time_spent_lectures",
    "time_spent_homework",
]

PROJECT_STAT_FIELDS = [
    "project_score",
    "project_learning_in_public_score",
    "peer_review_score",
    "peer_review_learning_in_public_score",
    "total_score",
    "time_spent",
]


def _calculate_field_distributions(submissions_data, fields):
    """Compute min/max/avg/quantiles per field from prefetched submission rows."""
    stats = {"total_submissions": len(submissions_data)}

    nones = {
        "min": None,
        "max": None,
        "avg": None,
        "q1": None,
        "median": None,
        "q3": None,
    }

    for field in fields:
        # Extract non-null values for this field from already fetched data
        values = [
            submission[field]
            for submission in submissions_data
            if submission[field] is not None
        ]

        if not values or len(values) < 3:
            stats[field] = nones
            continue

        quantiles = statistics.quantiles(
            values, n=4, method="inclusive"
        )

        stats[field] = {
            "min": min(values),
            "max": max(values),
            "avg": statistics.mean(values),
            "q1": quantiles[0],
            "median": quantiles[1],
            "q3": quantiles[2],
        }

    return stats


def _persist_field_stats(stats, calculated_stats, fields):
    """Copy the computed distribution for each field onto a stats model instance."""
    stats.total_submissions = calculated_stats["total_submissions"]

    for field in fields:
        field_stats = calculated_stats[field]

        setattr(stats, f"min_{field}", field_stats["min"])
        setattr(stats, f"max_{field}", field_stats["max"])
        setattr(stats, f"avg_{field}", field_stats["avg"])
        setattr(stats, f"median_{field}", field_stats["median"])
        setattr(stats, f"q1_{field}", field_stats["q1"])
        setattr(stats, f"q3_{field}", field_stats["q3"])


def calculate_raw_homework_statistics(homework):
    # Single query to get all the fields we need, avoiding the N+1 problem
    submissions_data = list(
        Submission.objects.filter(homework=homework).values(
            *HOMEWORK_STAT_FIELDS
        )
    )
    return _calculate_field_distributions(
        submissions_data, HOMEWORK_STAT_FIELDS
    )


def calculate_homework_statistics(homework, force=False):
    if homework.state != HomeworkState.SCORED.value:
        raise ValueError(
            f"Cannot calculate statistics for unscored homework {homework}"
        )

    stats, created = HomeworkStatistics.objects.get_or_create(
        homework=homework
    )

    if force or created:
        calculated_stats = calculate_raw_homework_statistics(homework)
        _persist_field_stats(
            stats, calculated_stats, HOMEWORK_STAT_FIELDS
        )
        stats.save()

    return stats


def calculate_raw_project_statistics(project):
    # Single query to get all the fields we need, avoiding the N+1 problem
    submissions_data = list(
        ProjectSubmission.objects.filter(project=project).values(
            *PROJECT_STAT_FIELDS
        )
    )
    return _calculate_field_distributions(
        submissions_data, PROJECT_STAT_FIELDS
    )


def calculate_project_statistics(project, force=False):
    if project.state != ProjectState.COMPLETED.value:
        raise ValueError(
            f"Cannot calculate statistics for uncompleted project {project}"
        )

    stats, created = ProjectStatistics.objects.get_or_create(
        project=project
    )

    if force or created:
        calculated_stats = calculate_raw_project_statistics(project)
        _persist_field_stats(
            stats, calculated_stats, PROJECT_STAT_FIELDS
        )
        stats.save()

    return stats


def _wrapped_total_hours(homework_submissions, project_submissions):
    """Sum capped (<=100h) time-spent across all submissions for the year."""
    homework_hours = homework_submissions.aggregate(
        total_lecture_hours=Sum(Least("time_spent_lectures", 100.0)),
        total_homework_hours=Sum(Least("time_spent_homework", 100.0)),
    )
    project_hours = project_submissions.aggregate(
        total_project_hours=Sum(Least("time_spent", 100.0))
    )

    total_hours = 0
    for value in (
        homework_hours["total_lecture_hours"],
        homework_hours["total_homework_hours"],
        project_hours["total_project_hours"],
    ):
        if value:
            total_hours += value

    return round(total_hours, 1) if total_hours else 0


def _wrapped_course_stats(enrollments, courses):
    """Per-course enrollment counts, sorted most-popular first."""
    course_stats_list = [
        {
            "title": course.title,
            "slug": course.slug,
            "enrollment_count": enrollments.filter(course=course).count(),
        }
        for course in courses
    ]
    course_stats_list.sort(
        key=lambda x: x["enrollment_count"], reverse=True
    )
    return course_stats_list


def _wrapped_leaderboard(enrollments):
    """Top-100 leaderboard, summing each student's score across courses."""
    user_scores = {}
    for enrollment in enrollments:
        entry = user_scores.setdefault(
            enrollment.student_id,
            {
                "student": enrollment.student,
                "total_score": 0,
                "display_name": enrollment.display_name,
            },
        )
        entry["total_score"] += enrollment.total_score or 0

    sorted_users = sorted(
        user_scores.values(),
        key=lambda x: x["total_score"],
        reverse=True,
    )[:100]

    return [
        {
            "rank": idx,
            "display_name": user_data["display_name"],
            "total_score": user_data["total_score"],
            "student_id": user_data["student"].id,
        }
        for idx, user_data in enumerate(sorted_users, start=1)
    ]


def _wrapped_total_hours(homework_submissions, project_submissions):
    homework_hours = sum(
        min(hw.time_spent_lectures or 0, 100.0)
        + min(hw.time_spent_homework or 0, 100.0)
        for hw in homework_submissions
    )
    project_hours = sum(
        min(proj.time_spent or 0, 100.0)
        for proj in project_submissions
    )
    return round(homework_hours + project_hours, 1)


def _wrapped_learning_in_public_count(
    homework_submissions,
    project_submissions,
):
    homework_links = sum(
        len(hw.learning_in_public_links)
        if hw.learning_in_public_links
        else 0
        for hw in homework_submissions
    )
    project_links = sum(
        len(proj.learning_in_public_links)
        if proj.learning_in_public_links
        else 0
        for proj in project_submissions
    )
    return homework_links + project_links


def _wrapped_faq_count(homework_submissions, project_submissions):
    homework_faqs = sum(
        1
        for hw in homework_submissions
        if hw.faq_contribution_url and hw.faq_contribution_url.strip()
    )
    project_faqs = sum(
        1
        for proj in project_submissions
        if proj.faq_contribution_url and proj.faq_contribution_url.strip()
    )
    return homework_faqs + project_faqs


def _wrapped_courses(enrollments):
    return [
        {
            "title": enrollment.course.title,
            "score": enrollment.total_score,
            "slug": enrollment.course.slug,
            "enrollment_id": enrollment.id,
        }
        for enrollment in enrollments
    ]


def _wrapped_certificates_count(enrollments):
    return sum(
        1
        for enrollment in enrollments
        if enrollment.certificate_url
        and enrollment.certificate_url.strip()
    )


def _wrapped_rank(student, leaderboard_data):
    return next(
        (
            entry["rank"]
            for entry in leaderboard_data
            if entry["student_id"] == student.id
        ),
        None,
    )


def _wrapped_total_points(enrollments):
    return sum(e.total_score or 0 for e in enrollments)


def _wrapped_display_name(student, enrollments):
    return enrollments[0].display_name if enrollments else student.username


def _build_user_wrapped_stat(
    stats,
    student,
    *,
    homework_submissions,
    project_submissions,
    enrollments,
    peer_reviews_count,
    leaderboard_data,
):
    """Build an (unsaved) UserWrappedStatistics row for one student."""
    return UserWrappedStatistics(
        wrapped=stats,
        user=student,
        total_points=_wrapped_total_points(enrollments),
        total_hours=_wrapped_total_hours(
            homework_submissions,
            project_submissions,
        ),
        homework_count=len(homework_submissions),
        project_count=len(project_submissions),
        peer_reviews_given=peer_reviews_count,
        learning_in_public_count=_wrapped_learning_in_public_count(
            homework_submissions,
            project_submissions,
        ),
        faq_contributions_count=_wrapped_faq_count(
            homework_submissions,
            project_submissions,
        ),
        certificates_earned=_wrapped_certificates_count(enrollments),
        courses=_wrapped_courses(enrollments),
        rank=_wrapped_rank(student, leaderboard_data),
        display_name=_wrapped_display_name(student, enrollments),
    )


def _wrapped_year_window(year):
    year_start = timezone.make_aware(datetime(year, 1, 1))
    year_end = timezone.make_aware(datetime(year, 12, 31, 23, 59, 59))
    return year_start, year_end


def _wrapped_activity_querysets(year_start, year_end):
    homework_submissions = Submission.objects.filter(
        submitted_at__gte=year_start, submitted_at__lte=year_end
    ).select_related(
        "homework", "homework__course", "enrollment", "student"
    )
    project_submissions = ProjectSubmission.objects.filter(
        submitted_at__gte=year_start, submitted_at__lte=year_end
    ).select_related(
        "project", "project__course", "enrollment", "student"
    )
    return homework_submissions, project_submissions


def _wrapped_active_students_and_enrollments(
    homework_submissions, project_submissions
):
    students_from_homeworks = {hw.student for hw in homework_submissions}
    students_from_projects = {
        proj.student for proj in project_submissions
    }
    students_with_activity = students_from_homeworks | students_from_projects

    enrollment_ids_from_homeworks = {
        hw.enrollment_id for hw in homework_submissions if hw.enrollment_id
    }
    enrollment_ids_from_projects = {
        proj.enrollment_id
        for proj in project_submissions
        if proj.enrollment_id
    }
    enrollment_ids = (
        enrollment_ids_from_homeworks | enrollment_ids_from_projects
    )

    enrollments = Enrollment.objects.filter(
        id__in=enrollment_ids
    ).select_related("course", "student")
    courses = {enrollment.course for enrollment in enrollments}
    return students_with_activity, enrollments, courses


def _persist_wrapped_platform_statistics(
    stats,
    *,
    students_with_activity,
    enrollments,
    courses,
    homework_submissions,
    project_submissions,
):
    stats.total_participants = len(students_with_activity)
    stats.total_enrollments = enrollments.count()
    stats.total_hours = _wrapped_total_hours(
        homework_submissions, project_submissions
    )
    stats.total_certificates = enrollments.exclude(
        Q(certificate_url__isnull=True) | Q(certificate_url="")
    ).count()
    stats.total_points = (
        enrollments.aggregate(total_score=Sum("total_score"))[
            "total_score"
        ]
        or 0
    )
    stats.course_stats = _wrapped_course_stats(enrollments, courses)

    leaderboard_data = _wrapped_leaderboard(enrollments)
    stats.leaderboard = leaderboard_data
    stats.save()
    return leaderboard_data


def _group_wrapped_activity_by_student(
    homework_submissions, project_submissions, enrollments
):
    homework_by_student = defaultdict(list)
    for homework_submission in homework_submissions:
        homework_by_student[homework_submission.student].append(
            homework_submission
        )

    project_by_student = defaultdict(list)
    for project_submission in project_submissions:
        project_by_student[project_submission.student].append(
            project_submission
        )

    enrollment_by_student = defaultdict(list)
    for enrollment in enrollments:
        enrollment_by_student[enrollment.student].append(enrollment)

    return homework_by_student, project_by_student, enrollment_by_student


def _wrapped_peer_review_counts(students_with_activity, year_start, year_end):
    peer_review_counts = {}
    peer_reviews = (
        PeerReview.objects.filter(
            reviewer__student__in=students_with_activity,
            submitted_at__gte=year_start,
            submitted_at__lte=year_end,
        )
        .values("reviewer__student")
        .annotate(count=Count("id"))
    )
    for peer_review in peer_reviews:
        peer_review_counts[peer_review["reviewer__student"]] = peer_review[
            "count"
        ]
    return peer_review_counts


def _build_user_wrapped_stats(
    stats,
    *,
    students_with_activity,
    homework_by_student,
    project_by_student,
    enrollment_by_student,
    peer_review_counts,
    leaderboard_data,
):
    return [
        _build_user_wrapped_stat(
            stats,
            student,
            homework_submissions=homework_by_student.get(student, []),
            project_submissions=project_by_student.get(student, []),
            enrollments=enrollment_by_student.get(student, []),
            peer_reviews_count=peer_review_counts.get(student.id, 0),
            leaderboard_data=leaderboard_data,
        )
        for student in students_with_activity
    ]


def _replace_user_wrapped_statistics(stats, user_stats_objects):
    UserWrappedStatistics.objects.filter(wrapped=stats).delete()
    UserWrappedStatistics.objects.bulk_create(
        user_stats_objects, batch_size=500
    )


def _wrapped_statistics_to_calculate(year, force):
    stats, created = WrappedStatistics.objects.get_or_create(year=year)
    if not force and not created:
        logger.info(
            f"Wrapped statistics for {year} already exist. Use force=True to recalculate."
        )
        return stats, False
    return stats, True


def _wrapped_activity_context(year):
    year_start, year_end = _wrapped_year_window(year)
    homework_submissions, project_submissions = (
        _wrapped_activity_querysets(year_start, year_end)
    )
    students_with_activity, enrollments, courses = (
        _wrapped_active_students_and_enrollments(
            homework_submissions,
            project_submissions,
        )
    )
    return {
        "year_start": year_start,
        "year_end": year_end,
        "homework_submissions": homework_submissions,
        "project_submissions": project_submissions,
        "students_with_activity": students_with_activity,
        "enrollments": enrollments,
        "courses": courses,
    }


def _persist_wrapped_user_statistics(stats, activity, leaderboard_data):
    homework_by_student, project_by_student, enrollment_by_student = (
        _group_wrapped_activity_by_student(
            activity["homework_submissions"],
            activity["project_submissions"],
            activity["enrollments"],
        )
    )
    peer_review_counts = _wrapped_peer_review_counts(
        activity["students_with_activity"],
        activity["year_start"],
        activity["year_end"],
    )
    user_stats_objects = _build_user_wrapped_stats(
        stats,
        students_with_activity=activity["students_with_activity"],
        homework_by_student=homework_by_student,
        project_by_student=project_by_student,
        enrollment_by_student=enrollment_by_student,
        peer_review_counts=peer_review_counts,
        leaderboard_data=leaderboard_data,
    )
    _replace_user_wrapped_statistics(stats, user_stats_objects)
    return user_stats_objects


def _calculate_wrapped_statistics(stats, year):
    logger.info(f"Calculating wrapped statistics for {year}...")
    start_time = time()

    activity = _wrapped_activity_context(year)
    leaderboard_data = _persist_wrapped_platform_statistics(
        stats,
        students_with_activity=activity["students_with_activity"],
        enrollments=activity["enrollments"],
        courses=activity["courses"],
        homework_submissions=activity["homework_submissions"],
        project_submissions=activity["project_submissions"],
    )

    logger.info(
        "Platform statistics calculated. Now calculating individual user statistics..."
    )
    user_stats_objects = _persist_wrapped_user_statistics(
        stats,
        activity,
        leaderboard_data,
    )

    _log_wrapped_statistics_calculated(
        year,
        start_time,
        user_stats_objects,
    )


def _log_wrapped_statistics_calculated(
    year,
    start_time,
    user_stats_objects,
):
    elapsed_time = time() - start_time
    logger.info(
        f"Wrapped statistics for {year} calculated successfully in {elapsed_time:.2f} seconds. "
        f"Processed {len(user_stats_objects)} users."
    )


def calculate_wrapped_statistics(year=2025, force=False):
    """
    Calculate and save wrapped statistics for a given year.
    This function pre-calculates all the statistics that would be needed
    for the wrapped page to avoid slow queries on page load.

    Args:
        year: The year to calculate statistics for (default: 2025)
        force: If True, recalculate even if statistics already exist

    Returns:
        WrappedStatistics object
    """
    stats, should_calculate = _wrapped_statistics_to_calculate(year, force)
    if not should_calculate:
        return stats

    _calculate_wrapped_statistics(stats, year)
    return stats
