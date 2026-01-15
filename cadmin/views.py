import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q

from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Project,
    ProjectState,
    Submission,
    ProjectSubmission,
    Question,
    Answer,
    PeerReview,
    PeerReviewState,
)
from courses.scoring import (
    score_homework_submissions,
    fill_correct_answers,
    calculate_homework_statistics,
    calculate_project_statistics,
)
from courses.projects import (
    assign_peer_reviews_for_project,
    score_project,
    ProjectActionStatus,
)

from collections import defaultdict

logger = logging.getLogger(__name__)


def staff_required(function):
    """Decorator to require staff/admin access"""
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated and u.is_staff,
        login_url="/accounts/login/",
    )
    return actual_decorator(function)


@staff_required
def course_list(request):
    """List all courses with admin actions"""
    courses = Course.objects.all().order_by("-id")
    
    context = {
        "courses": courses,
    }
    
    return render(request, "cadmin/course_list.html", context)


@staff_required
def course_admin(request, course_slug):
    """Admin panel for a specific course"""
    course = get_object_or_404(Course, slug=course_slug)
    
    # Get all homeworks for the course
    homeworks = Homework.objects.filter(course=course).order_by("due_date")
    
    # Get all projects for the course
    projects = Project.objects.filter(course=course).order_by("id")
    
    # Get statistics
    total_enrollments = course.enrollment_set.count()
    
    # Get completion statistics for homeworks
    for hw in homeworks:
        hw.submissions_count = Submission.objects.filter(homework=hw).count()
    
    # Get completion statistics for projects
    for proj in projects:
        proj.submissions_count = ProjectSubmission.objects.filter(project=proj).count()
    
    context = {
        "course": course,
        "homeworks": homeworks,
        "projects": projects,
        "total_enrollments": total_enrollments,
    }
    
    return render(request, "cadmin/course_admin.html", context)


@staff_required
def homework_score(request, course_slug, homework_slug):
    """Score a homework"""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(Homework, course=course, slug=homework_slug)
    
    status, message = score_homework_submissions(homework.id)
    
    if status:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    
    return redirect("cadmin_course", course_slug=course_slug)


@staff_required
def homework_set_correct_answers(request, course_slug, homework_slug):
    """Set correct answers to most popular for a homework"""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(Homework, course=course, slug=homework_slug)
    
    fill_correct_answers(homework)
    
    messages.success(
        request,
        f"Correct answers for {homework.title} set to most popular",
    )
    
    return redirect("cadmin_course", course_slug=course_slug)


@staff_required
def homework_submissions(request, course_slug, homework_slug):
    """View all submissions for a homework"""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    # Get all questions for this homework
    questions = Question.objects.filter(homework=homework).order_by("id")

    # Get all submissions for this homework with answers prefetched
    # to avoid N+1 queries
    submissions = (
        Submission.objects.filter(homework=homework)
        .select_related("student", "enrollment")
        .prefetch_related("answer_set__question")
        .order_by("-submitted_at")
    )

    # Build a list of submissions with their answers organized by question
    submissions_data = []
    for submission in submissions:
        # Create a map of question_id -> answer for this submission
        answer_map = {
            answer.question_id: answer 
            for answer in submission.answer_set.all()
        }
        
        # Build list of answers in question order
        answers = []
        for question in questions:
            answer = answer_map.get(question.id)
            answer_text = answer.answer_text if answer else ""
            answers.append(answer_text or "")
        
        submissions_data.append({
            "submission": submission,
            "answers": answers,
        })

    context = {
        "course": course,
        "homework": homework,
        "questions": questions,
        "submissions_data": submissions_data,
    }

    return render(request, "cadmin/homework_submissions.html", context)


@staff_required
def project_assign_reviews(request, course_slug, project_slug):
    """Assign peer reviews for a project"""
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(Project, course=course, slug=project_slug)
    
    status, message = assign_peer_reviews_for_project(project)
    
    if status == ProjectActionStatus.OK:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    
    return redirect("cadmin_course", course_slug=course_slug)


@staff_required
def project_score(request, course_slug, project_slug):
    """Score a project"""
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(Project, course=course, slug=project_slug)
    
    status, message = score_project(project)
    
    if status == ProjectActionStatus.OK:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    
    return redirect("cadmin_course", course_slug=course_slug)


@staff_required
def project_submissions(request, course_slug, project_slug):
    """View all submissions for a project"""
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    # Get all submissions for this project with related data prefetched
    # to avoid N+1 queries
    submissions = (
        ProjectSubmission.objects.filter(project=project)
        .select_related("student", "enrollment")
        .order_by("-submitted_at")
    )

    # Get peer review data for each submission
    # We need to count how many peer reviews each student has completed
    # out of the total assigned to them
    peer_reviews = PeerReview.objects.filter(
        reviewer__project=project
    ).select_related("reviewer")

    # Build a dictionary mapping submission_id to review counts
    # This is more efficient than nested loops
    review_counts = defaultdict(lambda: {'completed': 0, 'total': 0})
    
    for review in peer_reviews:
        if not review.optional:
            review_counts[review.reviewer_id]['total'] += 1
            if review.state == PeerReviewState.SUBMITTED.value:
                review_counts[review.reviewer_id]['completed'] += 1

    # Add review count data to each submission
    for submission in submissions:
        counts = review_counts[submission.id]
        submission.peer_reviews_completed = counts['completed']
        submission.peer_reviews_total = counts['total']

    context = {
        "course": course,
        "project": project,
        "submissions": submissions,
    }

    return render(request, "cadmin/project_submissions.html", context)

