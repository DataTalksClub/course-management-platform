import json
from collections import Counter
import yaml

from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from django.forms.models import model_to_dict
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required

from courses.models import (
    User, 
    Enrollment,
    Answer,
    Course,
    Homework,
    Project,
    ProjectSubmission,
    ReviewCriteria,
)


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

    # Get project data and add the points_to_pass property
    project_data = model_to_dict(project)
    project_data["points_to_pass"] = project.points_to_pass

    # Compile the result
    result = {
        "course": course_data,
        "project": project_data,
        "submissions": submission_data,
    }

    return JsonResponse(result)


@token_required
@csrf_exempt
def update_enrollment_certificate_view(request, course_slug: str):
    """
    Update enrollment certificate URL for a user in a specific course.

    Expected JSON payload:
    {
        "email": "user@example.com",
        "certificate_path": "/path/to/certificate.pdf"
    }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get("email")
        certificate_path = data.get("certificate_path")

        if not email or not certificate_path:
            return JsonResponse(
                {
                    "error": "Both email and certificate_path are required"
                },
                status=400,
            )

        # Find the course
        course = get_object_or_404(Course, slug=course_slug)

        # Find the user by email
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse(
                {"error": f"User with email {email} not found"},
                status=404,
            )

        # Find the enrollment
        try:
            enrollment = Enrollment.objects.get(
                student=user, course=course
            )
        except Enrollment.DoesNotExist:
            return JsonResponse(
                {
                    "error": f"User {email} is not enrolled in course {course_slug}"
                },
                status=404,
            )

        # Update the certificate URL
        enrollment.certificate_url = certificate_path
        enrollment.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Certificate URL updated for {email} in course {course_slug}",
                "enrollment_id": enrollment.id,
                "certificate_url": certificate_path,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def get_passed_enrollments(passed_project_submissions, min_projects):
    assert min_projects > 0, "min_projects must be greater than 0"

    counter_passed = Counter()
    ids_mapping = {}

    for s in passed_project_submissions:
        e = s.enrollment
        eid = e.id
        counter_passed[eid] += 1
        ids_mapping[eid] = e

    passed_enrollments = []

    for eid, count in counter_passed.items():
        if count >= min_projects:
            passed_enrollments.append(ids_mapping[eid])

    return passed_enrollments


@token_required
def graduates_data_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)

    passed_project_submissions = ProjectSubmission.objects.filter(
        project__course=course, passed=True
    ).prefetch_related("enrollment")

    passed_enrollments = get_passed_enrollments(
        passed_project_submissions, course.min_projects_to_pass
    )

    graduates = []

    for enrollment in passed_enrollments:
        student = enrollment.student
        email = student.email
        name = enrollment.certificate_name or enrollment.display_name

        graduates.append(
            {
                "email": email,
                "name": name,
            }
        )

    response = {"graduates": graduates}
    return JsonResponse(response)


def course_criteria_yaml_view(request, course_slug: str):
    """Return project criteria for a course in YAML format"""
    course = get_object_or_404(Course, slug=course_slug)
    
    # Get all review criteria for the course
    review_criteria = ReviewCriteria.objects.filter(
        course=course
    ).order_by('id')
    
    # Convert criteria to a structured format for YAML export
    criteria_data = {
        'course': {
            'slug': course.slug,
            'title': course.title,
            'description': course.description,
        },
        'review_criteria': []
    }
    
    for criteria in review_criteria:
        criteria_dict = {
            'description': criteria.description,
            'type': dict(criteria.REVIEW_CRITERIA_TYPES)[criteria.review_criteria_type],
            'review_criteria_type': criteria.review_criteria_type,
            'options': criteria.options
        }
        criteria_data['review_criteria'].append(criteria_dict)
    
    # Convert to YAML
    yaml_content = yaml.dump(
        criteria_data, 
        default_flow_style=False, 
        allow_unicode=True,
        sort_keys=False
    )
    
    # Return as HTTP response with content type that displays in browser
    response = HttpResponse(yaml_content, content_type='text/plain; charset=utf-8')
    # response['Content-Disposition'] = f'attachment; filename="{course_slug}-criteria.yaml"'
    
    return response
