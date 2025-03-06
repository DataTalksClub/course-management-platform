from django.http import JsonResponse
from accounts.auth import token_required
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch

from collections import Counter
from hashlib import sha1

from courses.models import (
    Answer,
    Course,
    Homework,
    Project,
    ProjectSubmission,
)

from django.forms.models import model_to_dict


@token_required
def homework_data_view(request, course_slug: str, homework_slug: str):
    course = get_object_or_404(Course, slug=course_slug)

    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    answers_prefetch = Prefetch(
        "answer_set", queryset=Answer.objects.all()
    )
    submissions = homework.submission_set.prefetch_related(
        answers_prefetch
    ).all()

    course_data = model_to_dict(
        course, exclude=["students", "first_homework_scored"]
    )

    submission_data = []
    for submission in submissions:
        submission_dict = {
            "student_id": submission.student_id,
            "homework_link": submission.homework_link,
            "learning_in_public_links": submission.learning_in_public_links,
            "time_spent_lectures": submission.time_spent_lectures,
            "time_spent_homework": submission.time_spent_homework,
            "problems_comments": submission.problems_comments,
            "faq_contribution": submission.faq_contribution,
            "questions_score": submission.questions_score,
            "faq_score": submission.faq_score,
            "learning_in_public_score": submission.learning_in_public_score,
            "total_score": submission.total_score,
            "answers": list(
                submission.answer_set.values(
                    "question_id", "answer_text", "is_correct"
                )
            ),
        }
        submission_data.append(submission_dict)

    result = {
        "course": course_data,
        "homework": model_to_dict(homework),
        "submissions": submission_data,
    }

    return JsonResponse(result)


@token_required
def project_data_view(request, course_slug: str, project_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    submissions = (
        ProjectSubmission.objects.filter(project=project)
        .prefetch_related("student", "enrollment")
        .all()
    )

    course_data = model_to_dict(
        course, exclude=["students", "first_homework_scored"]
    )

    submission_data = []
    for submission in submissions:
        submission_dict = {
            "student_id": submission.student_id,
            "student_email": submission.student.email,
            "github_link": submission.github_link,
            "commit_id": submission.commit_id,
            "learning_in_public_links": submission.learning_in_public_links,
            "faq_contribution": submission.faq_contribution,
            "time_spent": submission.time_spent,
            "problems_comments": submission.problems_comments,
            "project_score": submission.project_score,
            "project_faq_score": submission.project_faq_score,
            "project_learning_in_public_score": submission.project_learning_in_public_score,
            "peer_review_score": submission.peer_review_score,
            "peer_review_learning_in_public_score": submission.peer_review_learning_in_public_score,
            "total_score": submission.total_score,
            "reviewed_enough_peers": submission.reviewed_enough_peers,
            "passed": submission.passed,
        }
        submission_data.append(submission_dict)

    # Compile the result
    result = {
        "course": course_data,
        "project": model_to_dict(project),
        "submissions": submission_data,
    }

    return JsonResponse(result)

@token_required
def graduates_data_view(request, course_slug: str):
    cohort = 2024

    # Fetch course
    try:
        course = get_object_or_404(Course, slug=course_slug)
        #course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return JsonResponse({"error": "Course not found"}, status=404)

    # Get passed students
    graduates = ProjectSubmission.objects \
        .filter(project__course=course, passed=True) \
        .prefetch_related("enrollment")

    # Count projects per student
    cnt = Counter()
    ids_mapping = {}

    for g in graduates:
        e = g.enrollment
        eid = e.id
        cnt[eid] += 1
        ids_mapping[eid] = e

    passed = []
    for eid, c in cnt.items():
        if c >= min_projects:
            passed.append(ids_mapping[eid])

    # Prepare results
    results = []
    for enrollment in passed:
        student = enrollment.student
        email = student.email
        name = enrollment.certificate_name or enrollment.display_name

        results.append({
            "email": email,
            "name": name,
        })

    results.append({
        'email': 'never.give.up@gmail.com',
        'name': 'Rick Astley',
        'hash': 'na'
    })

    return JsonResponse(results, safe=False)
