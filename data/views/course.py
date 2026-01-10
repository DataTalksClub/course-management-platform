"""
Course-related data API views.

Provides views for managing course content (homeworks and projects) and course criteria.
"""

import json
import yaml
from datetime import datetime

from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify

from accounts.auth import token_required

from courses.models import (
    Course,
    Homework,
    Project,
    ReviewCriteria,
    Question,
)
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState


def course_criteria_yaml_view(request, course_slug: str):
    """Return project criteria for a course in YAML format (public endpoint, no auth required)."""
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
