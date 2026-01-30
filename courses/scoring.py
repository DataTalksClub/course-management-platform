import logging
import statistics

from time import time
from enum import Enum
from collections import defaultdict

from django.utils import timezone
from django.db.models import Sum, Count

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
        submission.faq_contribution
        and len(submission.faq_contribution) >= 5
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


def score_homework_submissions(
    homework_id: str,
) -> tuple[HomeworkScoringStatus, str]:
    with transaction.atomic():
        t0 = time()
        logger.info(f"Scoring submissions for homework {homework_id}")

        homework = Homework.objects.get(pk=homework_id)

        if homework.due_date > timezone.now():
            return (
                HomeworkScoringStatus.FAIL,
                f"The due date for {homework_id} is in the future. Update the due date to score.",
            )

        if homework.state == HomeworkState.CLOSED.value:
            return (
                HomeworkScoringStatus.FAIL,
                f"Homework {homework_id} is closed. Update the state to OPEN to score.",
            )

        if homework.state == HomeworkState.SCORED.value:
            return (
                HomeworkScoringStatus.FAIL,
                f"Homework {homework_id} is already scored.",
            )

        submissions = Submission.objects.filter(
            homework__id=homework_id
        )
        answers = Answer.objects.filter(
            submission__in=submissions
        ).select_related("question", "submission")

        answers_by_submission_id = defaultdict(list)
        for answer in answers:
            aid = answer.submission_id
            answers_by_submission_id[aid].append(answer)

        logger.info(
            f"Scoring {len(answers_by_submission_id)} submissions for homework {homework_id}"
        )

        for submission in submissions:
            submission_answers = answers_by_submission_id[submission.id]
            update_score(submission, submission_answers, save=False)

        logger.info(
            f"Updating the submissions for homework {homework_id}"
        )

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

        homework.state = HomeworkState.SCORED.value
        homework.save()

        logger.info(
            f"Scored {len(submissions)} submissions for homework {homework_id}"
        )

        course = homework.course
        update_leaderboard(course)

        course.first_homework_scored = True
        course.save()

        calculate_homework_statistics(homework, force=True)

        t1 = time()
        logger.info(f"Scored homework in {(t1 - t0):.2f} seconds")
        return (
            HomeworkScoringStatus.OK,
            f"Homework {homework_id} is scored",
        )


def update_leaderboard(course: Course):
    t0 = time()
    logger.info(f"Updating leaderboard for course {course.id}")

    homeworks = Homework.objects.filter(course=course)

    aggregated_homework_scores = (
        Submission.objects.filter(homework__in=homeworks)
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )
    homework_scores_by_enrollment = {
        score["enrollment"]: score["total_score"]
        for score in aggregated_homework_scores
    }

    projects = Project.objects.filter(course=course)

    aggregated_project_scores = (
        ProjectSubmission.objects.filter(project__in=projects)
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )

    project_score_by_enrollment = {
        score["enrollment"]: score["total_score"]
        for score in aggregated_project_scores
    }

    enrollments = list(Enrollment.objects.filter(course=course))

    for enrollment in enrollments:
        homework_score = homework_scores_by_enrollment.get(
            enrollment.id, 0
        )
        project_score = project_score_by_enrollment.get(
            enrollment.id, 0
        )

        enrollment.total_score = homework_score + project_score

    enrollments = sorted(
        enrollments, key=lambda x: x.total_score, reverse=True
    )

    for rank, enrollment in enumerate(enrollments, 1):
        enrollment.position_on_leaderboard = rank

    Enrollment.objects.bulk_update(
        enrollments,
        ["total_score", "position_on_leaderboard"],
    )

    # Invalidate the leaderboard cache
    cache_key = f"leaderboard:{course.id}"
    cache.delete(cache_key)
    logger.info(f"Invalidated cache for leaderboard of course {course.id}")

    t1 = time()
    logger.info(f"Updated leaderboard in {(t1 - t0):.2f} seconds")


def fill_most_common_answer_as_correct(question: Question) -> None:
    if question.correct_answer:
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


def fill_correct_answers(homework: Homework) -> None:
    questions = Question.objects.filter(homework=homework)

    for question in questions:
        fill_most_common_answer_as_correct(question)


def calculate_raw_homework_statistics(homework):
    # Fetch all needed fields in one query to avoid N+1 problem
    fields = [
        "questions_score",
        "learning_in_public_score",
        "total_score",
        "time_spent_lectures",
        "time_spent_homework",
    ]

    # Single query to get all data we need
    submissions_data = list(
        Submission.objects.filter(homework=homework).values(*fields)
    )

    total_submissions = len(submissions_data)
    stats = {"total_submissions": total_submissions}

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

        stats.total_submissions = calculated_stats["total_submissions"]

        for field in [
            "questions_score",
            "learning_in_public_score",
            "total_score",
            "time_spent_lectures",
            "time_spent_homework",
        ]:
            field_stats = calculated_stats[field]

            setattr(stats, f"min_{field}", field_stats["min"])
            setattr(stats, f"max_{field}", field_stats["max"])
            setattr(stats, f"avg_{field}", field_stats["avg"])
            setattr(stats, f"median_{field}", field_stats["median"])
            setattr(stats, f"q1_{field}", field_stats["q1"])
            setattr(stats, f"q3_{field}", field_stats["q3"])

        stats.save()

    return stats


def calculate_raw_project_statistics(project):
    # Fetch all needed fields in one query to avoid N+1 problem
    fields = [
        "project_score",
        "project_learning_in_public_score",
        "peer_review_score",
        "peer_review_learning_in_public_score",
        "total_score",
        "time_spent",
    ]

    # Single query to get all data we need
    submissions_data = list(
        ProjectSubmission.objects.filter(project=project).values(
            *fields
        )
    )

    total_submissions = len(submissions_data)
    stats = {"total_submissions": total_submissions}

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

        stats.total_submissions = calculated_stats["total_submissions"]

        for field in [
            "project_score",
            "project_learning_in_public_score",
            "peer_review_score",
            "peer_review_learning_in_public_score",
            "total_score",
            "time_spent",
        ]:
            field_stats = calculated_stats[field]

            setattr(stats, f"min_{field}", field_stats["min"])
            setattr(stats, f"max_{field}", field_stats["max"])
            setattr(stats, f"avg_{field}", field_stats["avg"])
            setattr(stats, f"median_{field}", field_stats["median"])
            setattr(stats, f"q1_{field}", field_stats["q1"])
            setattr(stats, f"q3_{field}", field_stats["q3"])

        stats.save()

    return stats


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
    from .models import WrappedStatistics, UserWrappedStatistics
    from .models.project import PeerReview
    from datetime import datetime
    from django.db.models import Q

    # Get or create the wrapped statistics object
    stats, created = WrappedStatistics.objects.get_or_create(year=year)

    if not force and not created:
        logger.info(
            f"Wrapped statistics for {year} already exist. Use force=True to recalculate."
        )
        return stats

    logger.info(f"Calculating wrapped statistics for {year}...")
    start_time = time()

    # Define year date range
    year_start = timezone.make_aware(datetime(year, 1, 1))
    year_end = timezone.make_aware(datetime(year, 12, 31, 23, 59, 59))

    # Get all homework submissions in the year
    homework_submissions_2025 = Submission.objects.filter(
        submitted_at__gte=year_start, submitted_at__lte=year_end
    ).select_related(
        "homework", "homework__course", "enrollment", "student"
    )

    # Get all project submissions in the year
    project_submissions_2025 = ProjectSubmission.objects.filter(
        submitted_at__gte=year_start, submitted_at__lte=year_end
    ).select_related(
        "project", "project__course", "enrollment", "student"
    )

    # Get unique students with activity in 2025
    students_from_homeworks = set(
        hw.student for hw in homework_submissions_2025
    )
    students_from_projects = set(
        proj.student for proj in project_submissions_2025
    )
    students_with_2025_activity = (
        students_from_homeworks | students_from_projects
    )

    # Get unique enrollments with activity in 2025
    enrollment_ids_from_homeworks = {
        hw.enrollment_id
        for hw in homework_submissions_2025
        if hw.enrollment_id
    }
    enrollment_ids_from_projects = {
        proj.enrollment_id
        for proj in project_submissions_2025
        if proj.enrollment_id
    }
    enrollment_ids_with_2025_activity = (
        enrollment_ids_from_homeworks | enrollment_ids_from_projects
    )

    # Get enrollments with 2025 activity (only those with submissions in the year)
    enrollments_for_active_students = Enrollment.objects.filter(
        id__in=enrollment_ids_with_2025_activity
    ).select_related("course", "student")

    # Get courses with activity in 2025 from these enrollments
    courses_with_2025_activity = {
        e.course for e in enrollments_for_active_students
    }

    # Calculate platform-wide statistics
    stats.total_participants = len(students_with_2025_activity)
    stats.total_enrollments = enrollments_for_active_students.count()

    # Calculate total hours with safeguards (max 100h per submission to avoid outliers)
    from django.db.models.functions import Least

    homework_hours = homework_submissions_2025.aggregate(
        total_lecture_hours=Sum(Least("time_spent_lectures", 100.0)),
        total_homework_hours=Sum(Least("time_spent_homework", 100.0)),
    )
    project_hours = project_submissions_2025.aggregate(
        total_project_hours=Sum(Least("time_spent", 100.0))
    )

    total_hours = 0
    if homework_hours["total_lecture_hours"]:
        total_hours += homework_hours["total_lecture_hours"]
    if homework_hours["total_homework_hours"]:
        total_hours += homework_hours["total_homework_hours"]
    if project_hours["total_project_hours"]:
        total_hours += project_hours["total_project_hours"]

    stats.total_hours = round(total_hours, 1) if total_hours else 0

    # Count certificates
    stats.total_certificates = enrollments_for_active_students.exclude(
        Q(certificate_url__isnull=True) | Q(certificate_url="")
    ).count()

    # Calculate total points
    stats.total_points = (
        enrollments_for_active_students.aggregate(
            total_score=Sum("total_score")
        )["total_score"]
        or 0
    )

    # Calculate course popularity
    course_stats_list = []
    for course in courses_with_2025_activity:
        enrollment_count = enrollments_for_active_students.filter(
            course=course
        ).count()
        course_stats_list.append(
            {
                "title": course.title,
                "slug": course.slug,
                "enrollment_count": enrollment_count,
            }
        )

    # Sort by enrollment count
    course_stats_list.sort(
        key=lambda x: x["enrollment_count"], reverse=True
    )
    stats.course_stats = course_stats_list

    # Calculate leaderboard (top 100)
    user_scores = {}
    for enrollment in enrollments_for_active_students:
        if enrollment.student_id not in user_scores:
            user_scores[enrollment.student_id] = {
                "student": enrollment.student,
                "total_score": 0,
                "display_name": enrollment.display_name,
            }
        user_scores[enrollment.student_id]["total_score"] += (
            enrollment.total_score or 0
        )

    # Sort and get top 100
    sorted_users = sorted(
        user_scores.values(),
        key=lambda x: x["total_score"],
        reverse=True,
    )[:100]

    leaderboard_data = []
    for idx, user_data in enumerate(sorted_users, start=1):
        leaderboard_data.append(
            {
                "rank": idx,
                "display_name": user_data["display_name"],
                "total_score": user_data["total_score"],
                "student_id": user_data["student"].id,
            }
        )

    stats.leaderboard = leaderboard_data
    stats.save()

    logger.info(
        "Platform statistics calculated. Now calculating individual user statistics..."
    )

    # Calculate individual user statistics
    # Delete old user statistics for this year
    UserWrappedStatistics.objects.filter(wrapped=stats).delete()

    # Pre-group submissions by student for efficiency
    homework_by_student = defaultdict(list)
    for hw in homework_submissions_2025:
        homework_by_student[hw.student].append(hw)

    project_by_student = defaultdict(list)
    for proj in project_submissions_2025:
        project_by_student[proj.student].append(proj)

    enrollment_by_student = defaultdict(list)
    for e in enrollments_for_active_students:
        enrollment_by_student[e.student].append(e)

    # Bulk fetch peer review counts for all students
    peer_review_counts = {}
    peer_reviews = (
        PeerReview.objects.filter(
            reviewer__student__in=students_with_2025_activity,
            submitted_at__gte=year_start,
            submitted_at__lte=year_end,
        )
        .values("reviewer__student")
        .annotate(count=Count("id"))
    )
    for pr in peer_reviews:
        peer_review_counts[pr["reviewer__student"]] = pr["count"]

    user_stats_objects = []
    for student in students_with_2025_activity:
        # Get user's submissions (now O(1) lookup)
        user_homework_submissions = homework_by_student.get(student, [])
        user_project_submissions = project_by_student.get(student, [])

        # Get user's enrollments (now O(1) lookup)
        user_enrollments = enrollment_by_student.get(student, [])

        # Calculate user hours (max 100h per submission to avoid outliers)
        user_homework_hours = sum(
            min(hw.time_spent_lectures or 0, 100.0)
            + min(hw.time_spent_homework or 0, 100.0)
            for hw in user_homework_submissions
        )
        user_total_hours = user_homework_hours + sum(
            min(proj.time_spent or 0, 100.0)
            for proj in user_project_submissions
        )

        # Get peer review count (pre-fetched)
        peer_reviews_count = peer_review_counts.get(student.id, 0)

        # Count learning in public
        lip_homework = sum(
            len(hw.learning_in_public_links)
            if hw.learning_in_public_links
            else 0
            for hw in user_homework_submissions
        )
        lip_projects = sum(
            len(proj.learning_in_public_links)
            if proj.learning_in_public_links
            else 0
            for proj in user_project_submissions
        )
        learning_in_public_count = lip_homework + lip_projects

        # Count FAQ contributions
        faq_homework = sum(
            1
            for hw in user_homework_submissions
            if hw.faq_contribution and hw.faq_contribution.strip()
        )
        faq_projects = sum(
            1
            for proj in user_project_submissions
            if proj.faq_contribution and proj.faq_contribution.strip()
        )
        faq_count = faq_homework + faq_projects

        # Get courses
        courses_list = [
            {
                "title": e.course.title,
                "score": e.total_score,
                "slug": e.course.slug,
                "enrollment_id": e.id,
            }
            for e in user_enrollments
        ]

        # Get certificates
        certificates_count = sum(
            1
            for e in user_enrollments
            if e.certificate_url and e.certificate_url.strip()
        )

        # Get total points
        total_points = sum(e.total_score or 0 for e in user_enrollments)

        # Get rank
        rank = None
        for lb_entry in leaderboard_data:
            if lb_entry["student_id"] == student.id:
                rank = lb_entry["rank"]
                break

        # Get display name
        display_name = (
            user_enrollments[0].display_name
            if user_enrollments
            else student.username
        )

        # Create user statistics object
        user_stat = UserWrappedStatistics(
            wrapped=stats,
            user=student,
            total_points=total_points,
            total_hours=round(user_total_hours, 1),
            homework_count=len(user_homework_submissions),
            project_count=len(user_project_submissions),
            peer_reviews_given=peer_reviews_count,
            learning_in_public_count=learning_in_public_count,
            faq_contributions_count=faq_count,
            certificates_earned=certificates_count,
            courses=courses_list,
            rank=rank,
            display_name=display_name,
        )
        user_stats_objects.append(user_stat)

    # Bulk create all user statistics
    UserWrappedStatistics.objects.bulk_create(
        user_stats_objects, batch_size=500
    )

    elapsed_time = time() - start_time
    logger.info(
        f"Wrapped statistics for {year} calculated successfully in {elapsed_time:.2f} seconds. "
        f"Processed {len(user_stats_objects)} users."
    )

    return stats
