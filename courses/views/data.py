import json
from collections import Counter
import yaml
from datetime import datetime

from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from django.forms.models import model_to_dict
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify

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
    Question,
)
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState


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


@token_required
@csrf_exempt
def course_content_view(request, course_slug: str):
    """
    Get or create homeworks and projects for a course.

    GET: Returns all homeworks and projects for the course.
    POST: Creates homeworks and projects with state=CLOSED.

    POST Expected JSON payload:
    {
        "homeworks": [
            {
                "name": "Homework 1",
                "slug": "homework-1",  // optional, auto-generated from name if not provided
                "due_date": "2025-03-15T23:59:59Z",
                "description": "Optional description",
                "questions": [
                    {
                        "text": "What is 2+2?",
                        "question_type": "MC",  // MULTIPLE_CHOICE, FREE_FORM, FREE_FORM_LONG, CHECKBOXES
                        "answer_type": "INT",    // ANY, FLOAT, INTEGER, EXACT_STRING, CONTAINS_STRING
                        "possible_answers": ["3", "4", "5"],
                        "correct_answer": "2",   // index (1-based) for MC/CB, actual value for others
                        "scores_for_correct_answer": 1
                    }
                ]
            }
        ],
        "projects": [
            {
                "name": "Project 1",
                "slug": "project-1",  // optional, auto-generated from name if not provided
                "submission_due_date": "2025-03-20T23:59:59Z",
                "peer_review_due_date": "2025-03-27T23:59:59Z",
                "description": "Optional description"
            }
        ]
    }

    All homeworks and projects will be created with state="CL" (CLOSED).
    """
    try:
        course = get_object_or_404(Course, slug=course_slug)

        # GET: Return all homeworks and projects
        if request.method == "GET":
            homeworks = Homework.objects.filter(course=course)
            projects = Project.objects.filter(course=course)

            homeworks_data = []
            for hw in homeworks:
                homeworks_data.append({
                    "id": hw.id,
                    "slug": hw.slug,
                    "title": hw.title,
                    "due_date": hw.due_date.isoformat(),
                    "state": hw.state,
                    "questions_count": hw.question_set.count(),
                })

            projects_data = []
            for proj in projects:
                projects_data.append({
                    "id": proj.id,
                    "slug": proj.slug,
                    "title": proj.title,
                    "submission_due_date": proj.submission_due_date.isoformat(),
                    "peer_review_due_date": proj.peer_review_due_date.isoformat(),
                    "state": proj.state,
                })

            return JsonResponse({
                "success": True,
                "course": course_slug,
                "homeworks": homeworks_data,
                "projects": projects_data,
            })

        # POST: Create new homeworks and projects
        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)

        data = json.loads(request.body)
        created_homeworks = []
        created_projects = []
        errors = []

        # Create homeworks
        homeworks_data = data.get("homeworks", [])
        for hw_data in homeworks_data:
            try:
                name = hw_data.get("name")
                due_date_str = hw_data.get("due_date")

                if not name or not due_date_str:
                    errors.append({"homework": hw_data, "error": "name and due_date are required"})
                    continue

                # Parse the due date
                try:
                    due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                except ValueError:
                    try:
                        due_date = datetime.strptime(due_date_str, "%Y-%m-%dT%H:%M:%SZ")
                    except ValueError:
                        errors.append({"homework": name, "error": f"Invalid date format: {due_date_str}"})
                        continue

                # Generate slug from name if not provided
                slug = hw_data.get("slug") or slugify(name)

                # Check if homework already exists
                if Homework.objects.filter(course=course, slug=slug).exists():
                    errors.append({"homework": name, "error": "Homework with this slug already exists"})
                    continue

                # Create homework as CLOSED
                homework = Homework.objects.create(
                    course=course,
                    slug=slug,
                    title=name,
                    description=hw_data.get("description", ""),
                    due_date=due_date,
                    state=HomeworkState.CLOSED.value,
                )

                # Create questions if provided
                questions_data = hw_data.get("questions", [])
                created_questions = []
                for q_data in questions_data:
                    try:
                        question = Question.objects.create(
                            homework=homework,
                            text=q_data.get("text", ""),
                            question_type=q_data.get("question_type", "FF"),
                            answer_type=q_data.get("answer_type"),
                            possible_answers="\n".join(q_data.get("possible_answers", [])),
                            correct_answer=q_data.get("correct_answer", ""),
                            scores_for_correct_answer=q_data.get("scores_for_correct_answer", 1),
                        )
                        created_questions.append({
                            "id": question.id,
                            "text": question.text,
                        })
                    except Exception as e:
                        errors.append({"homework": name, "question": q_data.get("text"), "error": str(e)})

                created_homeworks.append({
                    "id": homework.id,
                    "slug": homework.slug,
                    "title": homework.title,
                    "due_date": homework.due_date.isoformat(),
                    "state": homework.state,
                    "questions_count": len(created_questions),
                })

            except Exception as e:
                errors.append({"homework": hw_data.get("name", "unknown"), "error": str(e)})

        # Create projects
        projects_data = data.get("projects", [])
        for proj_data in projects_data:
            try:
                name = proj_data.get("name")
                submission_due_date_str = proj_data.get("submission_due_date")
                peer_review_due_date_str = proj_data.get("peer_review_due_date")

                if not name or not submission_due_date_str or not peer_review_due_date_str:
                    errors.append({
                        "project": name,
                        "error": "name, submission_due_date, and peer_review_due_date are required"
                    })
                    continue

                # Parse the dates
                try:
                    submission_due_date = datetime.fromisoformat(submission_due_date_str.replace('Z', '+00:00'))
                except ValueError:
                    try:
                        submission_due_date = datetime.strptime(submission_due_date_str, "%Y-%m-%dT%H:%M:%SZ")
                    except ValueError:
                        errors.append({"project": name, "error": f"Invalid submission_due_date format: {submission_due_date_str}"})
                        continue

                try:
                    peer_review_due_date = datetime.fromisoformat(peer_review_due_date_str.replace('Z', '+00:00'))
                except ValueError:
                    try:
                        peer_review_due_date = datetime.strptime(peer_review_due_date_str, "%Y-%m-%dT%H:%M:%SZ")
                    except ValueError:
                        errors.append({"project": name, "error": f"Invalid peer_review_due_date format: {peer_review_due_date_str}"})
                        continue

                # Generate slug from name if not provided
                slug = proj_data.get("slug") or slugify(name)

                # Check if project already exists
                if Project.objects.filter(course=course, slug=slug).exists():
                    errors.append({"project": name, "error": "Project with this slug already exists"})
                    continue

                # Create project as CLOSED
                project = Project.objects.create(
                    course=course,
                    slug=slug,
                    title=name,
                    description=proj_data.get("description", ""),
                    submission_due_date=submission_due_date,
                    peer_review_due_date=peer_review_due_date,
                    state=ProjectState.CLOSED.value,
                )

                created_projects.append({
                    "id": project.id,
                    "slug": project.slug,
                    "title": project.title,
                    "submission_due_date": project.submission_due_date.isoformat(),
                    "peer_review_due_date": project.peer_review_due_date.isoformat(),
                    "state": project.state,
                })

            except Exception as e:
                errors.append({"project": proj_data.get("name", "unknown"), "error": str(e)})

        return JsonResponse({
            "success": True,
            "course": course_slug,
            "created_homeworks": created_homeworks,
            "created_projects": created_projects,
            "errors": errors,
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Http404:
        return JsonResponse({"error": "Course not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# Backwards compatible alias
create_course_content_view = course_content_view


@token_required
@csrf_exempt
def homework_content_view(request, course_slug: str, homework_slug: str):
    """
    Get or create questions for a homework.

    GET: Returns homework details and all questions.
    POST: Creates questions for the homework and optionally updates state.

    POST Expected JSON payload:
    {
        "questions": [
            {
                "text": "What is 2+2?",
                "question_type": "MC",
                "answer_type": "INT",
                "possible_answers": ["3", "4", "5"],
                "correct_answer": "2",
                "scores_for_correct_answer": 1
            }
        ],
        "state": "OP"  // Optional: Update homework state (CL=closed, OP=open, SC=scored)
    }
    """
    try:
        course = get_object_or_404(Course, slug=course_slug)
        homework = get_object_or_404(Homework, course=course, slug=homework_slug)

        # GET: Return homework details and questions
        if request.method == "GET":
            questions = Question.objects.filter(homework=homework).order_by('id')

            questions_data = []
            for q in questions:
                questions_data.append({
                    "id": q.id,
                    "text": q.text,
                    "question_type": q.question_type,
                    "answer_type": q.answer_type,
                    "possible_answers": q.get_possible_answers(),
                    "correct_answer": q.correct_answer,
                    "scores_for_correct_answer": q.scores_for_correct_answer,
                })

            return JsonResponse({
                "success": True,
                "course": course_slug,
                "homework": {
                    "id": homework.id,
                    "slug": homework.slug,
                    "title": homework.title,
                    "description": homework.description,
                    "due_date": homework.due_date.isoformat(),
                    "state": homework.state,
                    "learning_in_public_cap": homework.learning_in_public_cap,
                    "homework_url_field": homework.homework_url_field,
                    "time_spent_lectures_field": homework.time_spent_lectures_field,
                    "time_spent_homework_field": homework.time_spent_homework_field,
                    "faq_contribution_field": homework.faq_contribution_field,
                },
                "questions": questions_data,
            })

        # POST: Create new questions and optionally update state
        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)

        data = json.loads(request.body)

        # Update homework state if provided
        state_updated = False
        new_state = data.get("state")
        if new_state:
            valid_states = [s.value for s in HomeworkState]
            if new_state not in valid_states:
                return JsonResponse({
                    "error": f"Invalid state. Must be one of: {valid_states}"
                }, status=400)
            old_state = homework.state
            homework.state = new_state
            homework.save()
            state_updated = True

        questions_data = data.get("questions", [])
        created_questions = []
        errors = []

        for q_data in questions_data:
            try:
                question = Question.objects.create(
                    homework=homework,
                    text=q_data.get("text", ""),
                    question_type=q_data.get("question_type", "FF"),
                    answer_type=q_data.get("answer_type"),
                    possible_answers="\n".join(q_data.get("possible_answers", [])),
                    correct_answer=q_data.get("correct_answer", ""),
                    scores_for_correct_answer=q_data.get("scores_for_correct_answer", 1),
                )
                created_questions.append({
                    "id": question.id,
                    "text": question.text,
                    "question_type": question.question_type,
                })
            except Exception as e:
                errors.append({
                    "question": q_data.get("text", "unknown"),
                    "error": str(e)
                })

        response_data = {
            "success": True,
            "course": course_slug,
            "homework": homework_slug,
            "created_questions": created_questions,
            "errors": errors,
        }

        if state_updated:
            response_data["homework_state"] = {
                "old": old_state,
                "new": new_state
            }

        return JsonResponse(response_data)

    except Http404:
        return JsonResponse({"error": "Course or homework not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
