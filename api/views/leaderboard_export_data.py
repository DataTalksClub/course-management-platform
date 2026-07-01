from django.core.paginator import Paginator
from django.db.models import Prefetch, Value
from django.db.models.functions import Coalesce
from django.urls import reverse

from courses.models import Enrollment, ProjectSubmission, Submission
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState

LEADERBOARD_DATA_PAGE_SIZE = 100


def leaderboard_yaml_page_url(course, page_number):
    url = reverse(
        "api_course_leaderboard",
        kwargs={"course_slug": course.slug},
    )
    return f"{url}?page={page_number}"


def leaderboard_homework_entry(sub):
    entry = {
        "homework": sub.homework.title,
        "homework_slug": sub.homework.slug,
        "total_score": sub.total_score,
        "questions_score": sub.questions_score,
        "faq_score": sub.faq_score,
        "learning_in_public_score": sub.learning_in_public_score,
    }
    if sub.homework_link:
        entry["homework_link"] = sub.homework_link
    if sub.faq_contribution_url:
        entry["faq_contribution_url"] = sub.faq_contribution_url
    if sub.learning_in_public_links:
        entry["learning_in_public_links"] = sub.learning_in_public_links
    return entry


def leaderboard_project_entry(sub):
    entry = {
        "project": sub.project.title,
        "project_slug": sub.project.slug,
        "total_score": sub.total_score,
        "project_score": sub.project_score,
        "peer_review_score": sub.peer_review_score,
        "project_learning_in_public_score": sub.project_learning_in_public_score,
        "peer_review_learning_in_public_score": sub.peer_review_learning_in_public_score,
        "project_faq_score": sub.project_faq_score,
        "passed": sub.passed,
    }
    if sub.github_link:
        entry["github_link"] = sub.github_link
    if sub.faq_contribution_url:
        entry["faq_contribution_url"] = sub.faq_contribution_url
    if sub.learning_in_public_links:
        entry["learning_in_public_links"] = sub.learning_in_public_links
    return entry


def leaderboard_submission_prefetches():
    scored_submissions = (
        Submission.objects.filter(
            homework__state=HomeworkState.SCORED.value,
        )
        .select_related("homework")
        .order_by("homework__id")
    )
    completed_project_submissions = (
        ProjectSubmission.objects.filter(
            project__state=ProjectState.COMPLETED.value,
            volunteer_review_only=False,
        )
        .select_related("project")
        .order_by("project__id")
    )
    homework_prefetch = Prefetch(
        "submission_set",
        queryset=scored_submissions,
        to_attr="scored_submissions",
    )
    project_prefetch = Prefetch(
        "projectsubmission_set",
        queryset=completed_project_submissions,
        to_attr="completed_project_submissions",
    )
    return (
        homework_prefetch,
        project_prefetch,
    )


def leaderboard_enrollments(course):
    prefetches = leaderboard_submission_prefetches()
    empty_position = Value(999999)
    leaderboard_position = Coalesce(
        "position_on_leaderboard",
        empty_position,
    )
    return (
        Enrollment.objects.filter(
            course=course,
            display_on_leaderboard=True,
        )
        .select_related("student")
        .prefetch_related(*prefetches)
        .order_by(
            leaderboard_position,
            "id",
        )
    )


def leaderboard_enrollment_entry(enrollment):
    hw_data = []
    scored_submissions = enrollment.scored_submissions
    for submission in scored_submissions:
        homework_entry = leaderboard_homework_entry(submission)
        hw_data.append(homework_entry)

    proj_data = []
    completed_submissions = enrollment.completed_project_submissions
    for submission in completed_submissions:
        project_entry = leaderboard_project_entry(submission)
        proj_data.append(project_entry)

    entry = {
        "position": enrollment.position_on_leaderboard,
        "display_name": enrollment.display_name,
        "total_score": enrollment.total_score,
    }
    if hw_data:
        entry["homeworks"] = hw_data
    if proj_data:
        entry["projects"] = proj_data
    return entry


def leaderboard_page_links(course, page_obj):
    next_page_number = None
    if page_obj.has_next():
        next_page_number = page_obj.next_page_number()
    previous_page_number = None
    if page_obj.has_previous():
        previous_page_number = page_obj.previous_page_number()

    next_page = None
    if next_page_number:
        next_page = leaderboard_yaml_page_url(course, next_page_number)
    previous_page = None
    if previous_page_number:
        previous_page = leaderboard_yaml_page_url(
            course,
            previous_page_number,
        )

    return {
        "next_page": next_page,
        "next_page_number": next_page_number,
        "previous_page": previous_page,
        "previous_page_number": previous_page_number,
    }


def build_leaderboard_data(course, page_number):
    leaderboard_queryset = leaderboard_enrollments(course)
    paginator = Paginator(
        leaderboard_queryset,
        LEADERBOARD_DATA_PAGE_SIZE,
    )
    page_obj = paginator.get_page(page_number)
    results = []
    enrollments = page_obj.object_list
    for enrollment in enrollments:
        enrollment_entry = leaderboard_enrollment_entry(enrollment)
        results.append(enrollment_entry)

    has_next = page_obj.has_next()
    has_previous = page_obj.has_previous()
    page_links = leaderboard_page_links(course, page_obj)
    data = {
        "course": course.slug,
        "page": page_obj.number,
        "total_pages": paginator.num_pages,
        "total_entries": paginator.count,
        "has_next": has_next,
        "has_previous": has_previous,
    }
    data.update(page_links)
    data["leaderboard"] = results
    return data
