import logging

from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test

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
    ReviewCriteria,
    ProjectEvaluationScore,
    Enrollment,
)
from courses.scoring import (
    score_homework_submissions,
    fill_correct_answers,
    update_leaderboard,
)
from courses.projects import (
    assign_peer_reviews_for_project,
    score_project,
    ProjectActionStatus,
)

logger = logging.getLogger(__name__)
CADMIN_PAGE_SIZE = 25


def paginate_queryset(request, queryset, per_page=CADMIN_PAGE_SIZE):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def pagination_querystring(request):
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"&{encoded}" if encoded else ""


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

    homeworks = list(Homework.objects.filter(course=course).order_by("due_date"))
    projects = list(Project.objects.filter(course=course).order_by("id"))
    total_enrollments = course.enrollment_set.count()

    homework_needing_score = []
    for hw in homeworks:
        hw.submissions_count = Submission.objects.filter(homework=hw).count()
        hw.can_score = hw.state in [
            HomeworkState.OPEN.value,
            HomeworkState.CLOSED.value,
        ]
        if hw.can_score and hw.submissions_count:
            homework_needing_score.append(hw)

    projects_needing_reviews = []
    projects_needing_score = []
    for proj in projects:
        proj.submissions_count = ProjectSubmission.objects.filter(project=proj).count()
        proj.needs_review_assignment = (
            proj.state == ProjectState.COLLECTING_SUBMISSIONS.value
        )
        proj.needs_scoring = proj.state == ProjectState.PEER_REVIEWING.value
        if proj.needs_review_assignment:
            projects_needing_reviews.append(proj)
        if proj.needs_scoring:
            projects_needing_score.append(proj)

    enrollments = Enrollment.objects.filter(course=course)
    support_metrics = {
        "disabled_lip": enrollments.filter(disable_learning_in_public=True).count(),
        "zero_score": enrollments.filter(total_score=0).count(),
        "hidden_leaderboard": enrollments.filter(display_on_leaderboard=False).count(),
    }
    needs_attention_count = (
        len(homework_needing_score)
        + len(projects_needing_reviews)
        + len(projects_needing_score)
        + support_metrics["disabled_lip"]
        + support_metrics["hidden_leaderboard"]
    )
    project_action_count = len(projects_needing_reviews) + len(projects_needing_score)

    context = {
        "course": course,
        "homeworks": homeworks,
        "projects": projects,
        "total_enrollments": total_enrollments,
        "homework_needing_score": homework_needing_score,
        "projects_needing_reviews": projects_needing_reviews,
        "projects_needing_score": projects_needing_score,
        "project_action_count": project_action_count,
        "support_metrics": support_metrics,
        "needs_attention_count": needs_attention_count,
    }

    return render(request, "cadmin/course_admin.html", context)


@staff_required
def homework_score(request, course_slug, homework_slug):
    """Score a homework"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
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
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
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

    search_query = request.GET.get("q", "").strip()

    submissions = (
        Submission.objects.filter(homework=homework)
        .select_related("student", "enrollment")
        .prefetch_related("answer_set__question")
        .order_by("-submitted_at")
    )

    if search_query:
        submissions = submissions.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
        )

    submissions_page = paginate_queryset(request, submissions)

    submissions_data = []
    for submission in submissions_page.object_list:
        answer_map = {
            answer.question_id: answer 
            for answer in submission.answer_set.all()
        }

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
        "submissions_page": submissions_page,
        "search_query": search_query,
        "pagination_querystring": pagination_querystring(request),
    }

    return render(request, "cadmin/homework_submissions.html", context)


@staff_required
def homework_submission_edit(request, course_slug, homework_slug, submission_id):
    """Edit a homework submission"""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(Homework, course=course, slug=homework_slug)
    submission = get_object_or_404(
        Submission, 
        id=submission_id, 
        homework=homework
    )
    
    # Get all questions for this homework
    questions = Question.objects.filter(homework=homework).order_by("id")
    
    # Get all answers for this submission
    answers = Answer.objects.filter(submission=submission).select_related("question")
    answer_map = {answer.question_id: answer for answer in answers}
    
    # Build a list of questions with their current answers
    questions_with_answers = []
    for question in questions:
        answer = answer_map.get(question.id)
        questions_with_answers.append({
            'question': question,
            'answer': answer,
            'answer_text': answer.answer_text if answer else "",
        })
    
    if request.method == "POST":
        # Store the old score to check if it changed
        old_total_score = submission.total_score
        
        try:
            # Update answers
            for question in questions:
                answer_text = request.POST.get(f"answer_{question.id}", "")
                
                # Get or create the answer
                answer, created = Answer.objects.get_or_create(
                    submission=submission,
                    question=question,
                    defaults={'answer_text': answer_text}
                )
                
                if not created:
                    answer.answer_text = answer_text
                    answer.save()
            
            # Update learning in public links
            lip_links_str = request.POST.get("learning_in_public_links", "")
            if lip_links_str.strip():
                # Parse the links (comma-separated)
                links = [link.strip() for link in lip_links_str.split(",") if link.strip()]
                submission.learning_in_public_links = links
            else:
                submission.learning_in_public_links = None
            
            # Recalculate the score
            from courses.scoring import update_score
            
            # Get updated answers
            updated_answers = list(Answer.objects.filter(submission=submission).select_related("question"))
            update_score(submission, updated_answers, save=True)
            
            # If the score changed, update the leaderboard
            if submission.total_score != old_total_score:
                update_leaderboard(course)
            
            messages.success(
                request,
                f"Homework submission for {submission.student.username} updated successfully",
            )
            return redirect("cadmin_homework_submissions", course_slug=course_slug, homework_slug=homework_slug)
        except Exception as e:
            messages.error(request, f"Error updating submission: {e}")
    
    context = {
        "course": course,
        "homework": homework,
        "submission": submission,
        "questions_with_answers": questions_with_answers,
    }
    
    return render(request, "cadmin/homework_submission_edit.html", context)


@staff_required
def project_assign_reviews(request, course_slug, project_slug):
    """Assign peer reviews for a project"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
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
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
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
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")

    submissions = (
        ProjectSubmission.objects.filter(project=project)
        .select_related("student", "enrollment")
        .order_by("-submitted_at")
    )

    if search_query:
        submissions = submissions.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
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

    submissions = list(submissions)
    for submission in submissions:
        counts = review_counts[submission.id]
        submission.peer_reviews_completed = counts['completed']
        submission.peer_reviews_total = counts['total']

    project_filter_counts = {
        "all": len(submissions),
        "incomplete_reviews": sum(
            1
            for submission in submissions
            if submission.peer_reviews_completed < submission.peer_reviews_total
        ),
        "missing_repository": sum(
            1 for submission in submissions if not submission.github_link
        ),
        "unscored": sum(
            1 for submission in submissions if submission.total_score is None
        ),
        "not_passed": sum(
            1 for submission in submissions if submission.passed is False
        ),
    }

    if status_filter == "incomplete-reviews":
        submissions = [
            submission
            for submission in submissions
            if submission.peer_reviews_completed < submission.peer_reviews_total
        ]
    elif status_filter == "missing-repository":
        submissions = [
            submission for submission in submissions if not submission.github_link
        ]
    elif status_filter == "unscored":
        submissions = [
            submission for submission in submissions if submission.total_score is None
        ]
    elif status_filter == "not-passed":
        submissions = [submission for submission in submissions if submission.passed is False]

    submissions_page = paginate_queryset(request, submissions)

    context = {
        "course": course,
        "project": project,
        "submissions": submissions_page.object_list,
        "submissions_page": submissions_page,
        "project_filter_counts": project_filter_counts,
        "search_query": search_query,
        "status_filter": status_filter,
        "pagination_querystring": pagination_querystring(request),
    }

    return render(request, "cadmin/project_submissions.html", context)


@staff_required
def project_submission_edit(request, course_slug, project_slug, submission_id):
    """Edit a project submission"""
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(Project, course=course, slug=project_slug)
    submission = get_object_or_404(
        ProjectSubmission, 
        id=submission_id, 
        project=project
    )
    
    # Get all review criteria for this course
    review_criteria = ReviewCriteria.objects.filter(course=course).order_by('id')
    
    # Get existing evaluation scores for this submission
    evaluation_scores = {
        score.review_criteria_id: score 
        for score in ProjectEvaluationScore.objects.filter(submission=submission)
    }
    
    # Build a list of criteria with their current scores
    criteria_with_scores = []
    for criteria in review_criteria:
        score_obj = evaluation_scores.get(criteria.id)
        criteria_with_scores.append({
            'criteria': criteria,
            'score': score_obj.score if score_obj else 0,
            'score_id': score_obj.id if score_obj else None,
        })

    if request.method == "POST":
        # Update the submission fields
        try:
            # Update or create evaluation scores for each criteria
            project_score = 0
            for criteria in review_criteria:
                score_value_str = request.POST.get(f"criteria_score_{criteria.id}", "0")
                try:
                    score_value = int(score_value_str)
                    if score_value < 0:
                        raise ValueError(f"Score for {criteria.description} cannot be negative")
                except (ValueError, TypeError):
                    raise ValueError(f"Invalid score for {criteria.description}: {score_value_str}")
                
                project_score += score_value
                
                # Update or create the evaluation score
                ProjectEvaluationScore.objects.update_or_create(
                    submission=submission,
                    review_criteria=criteria,
                    defaults={'score': score_value}
                )
            
            # Update the aggregate project score
            submission.project_score = project_score
            
            # Update other scores
            submission.project_faq_score = int(request.POST.get("project_faq_score", 0))
            submission.project_learning_in_public_score = int(request.POST.get("project_learning_in_public_score", 0))
            submission.peer_review_score = int(request.POST.get("peer_review_score", 0))
            submission.peer_review_learning_in_public_score = int(request.POST.get("peer_review_learning_in_public_score", 0))
            
            # Calculate total score from all components
            submission.total_score = (
                submission.project_score +
                submission.project_faq_score +
                submission.project_learning_in_public_score +
                submission.peer_review_score +
                submission.peer_review_learning_in_public_score
            )
            
            submission.reviewed_enough_peers = request.POST.get("reviewed_enough_peers") == "on"
            submission.passed = request.POST.get("passed") == "on"
            
            submission.save()
            
            messages.success(
                request,
                f"Project submission for {submission.student.username} updated successfully",
            )
            return redirect("cadmin_project_submissions", course_slug=course_slug, project_slug=project_slug)
        except ValueError as e:
            messages.error(request, f"Error updating submission: {e}")

    context = {
        "course": course,
        "project": project,
        "submission": submission,
        "criteria_with_scores": criteria_with_scores,
    }

    return render(request, "cadmin/project_submission_edit.html", context)


@staff_required
def enrollments_list(request, course_slug):
    """List all enrollments for a course"""
    course = get_object_or_404(Course, slug=course_slug)
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")

    enrollments_queryset = (
        Enrollment.objects.filter(course=course)
        .select_related("student")
        .annotate(
            homework_count=Count("submission", distinct=True),
            project_count=Count("projectsubmission", distinct=True),
        )
        .order_by("position_on_leaderboard", "id")
    )
    if search_query:
        enrollments_queryset = enrollments_queryset.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
            | Q(display_name__icontains=search_query)
        )

    enrollments = list(enrollments_queryset)
    enrollment_filter_counts = {
        "all": len(enrollments),
        "lip_disabled": sum(
            1 for enrollment in enrollments if enrollment.disable_learning_in_public
        ),
        "zero_score": sum(1 for enrollment in enrollments if enrollment.total_score == 0),
        "hidden": sum(
            1 for enrollment in enrollments if not enrollment.display_on_leaderboard
        ),
        "no_submissions": sum(
            1
            for enrollment in enrollments
            if enrollment.homework_count == 0 and enrollment.project_count == 0
        ),
    }
    for enrollment in enrollments:
        enrollment.has_no_submissions = (
            enrollment.homework_count == 0 and enrollment.project_count == 0
        )
        enrollment.has_support_flags = (
            enrollment.disable_learning_in_public
            or not enrollment.display_on_leaderboard
            or enrollment.has_no_submissions
        )

    if status_filter == "lip-disabled":
        enrollments = [
            enrollment for enrollment in enrollments if enrollment.disable_learning_in_public
        ]
    elif status_filter == "zero-score":
        enrollments = [enrollment for enrollment in enrollments if enrollment.total_score == 0]
    elif status_filter == "hidden":
        enrollments = [
            enrollment for enrollment in enrollments if not enrollment.display_on_leaderboard
        ]
    elif status_filter == "no-submissions":
        enrollments = [enrollment for enrollment in enrollments if enrollment.has_no_submissions]

    enrollments_page = paginate_queryset(request, enrollments)

    context = {
        "course": course,
        "enrollments": enrollments_page.object_list,
        "enrollments_page": enrollments_page,
        "total_enrollments": len(enrollments),
        "enrollment_filter_counts": enrollment_filter_counts,
        "search_query": search_query,
        "status_filter": status_filter,
        "pagination_querystring": pagination_querystring(request),
    }

    return render(request, "cadmin/enrollments.html", context)


@staff_required
def enrollment_edit(request, course_slug, enrollment_id):
    """Edit an enrollment - mainly to disable learning in public"""
    course = get_object_or_404(Course, slug=course_slug)
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, course=course)
    
    if request.method == "POST":
        # Handle the disable learning in public toggle
        action = request.POST.get("action")
        
        if action == "toggle_learning_in_public":
            # Toggle the flag
            enrollment.disable_learning_in_public = not enrollment.disable_learning_in_public
            enrollment.save()
            
            # If we're disabling, zero out all learning in public scores
            if enrollment.disable_learning_in_public:
                # Zero out homework learning in public scores
                homework_submissions = list(Submission.objects.filter(enrollment=enrollment))
                submissions_to_update = []
                for submission in homework_submissions:
                    if submission.learning_in_public_score > 0:
                        submission.learning_in_public_score = 0
                        # Recalculate total score
                        submission.total_score = (
                            submission.questions_score + 
                            submission.faq_score + 
                            submission.learning_in_public_score
                        )
                        submissions_to_update.append(submission)
                
                if submissions_to_update:
                    Submission.objects.bulk_update(
                        submissions_to_update,
                        ['learning_in_public_score', 'total_score']
                    )
                
                # Zero out project learning in public scores
                project_submissions = list(ProjectSubmission.objects.filter(enrollment=enrollment))
                project_submissions_to_update = []
                for submission in project_submissions:
                    if submission.project_learning_in_public_score > 0 or submission.peer_review_learning_in_public_score > 0:
                        submission.project_learning_in_public_score = 0
                        submission.peer_review_learning_in_public_score = 0
                        # Recalculate total score
                        submission.total_score = (
                            submission.project_score +
                            submission.project_faq_score +
                            submission.project_learning_in_public_score +
                            submission.peer_review_score +
                            submission.peer_review_learning_in_public_score
                        )
                        project_submissions_to_update.append(submission)
                
                if project_submissions_to_update:
                    ProjectSubmission.objects.bulk_update(
                        project_submissions_to_update,
                        ['project_learning_in_public_score', 'peer_review_learning_in_public_score', 'total_score']
                    )
                
                messages.success(
                    request,
                    f"Learning in public disabled for {enrollment.student.username}. All scores zeroed out."
                )
            else:
                messages.success(
                    request,
                    f"Learning in public re-enabled for {enrollment.student.username}. You may need to re-score homework and projects."
                )
            
            # Recalculate the leaderboard for the course
            update_leaderboard(course)
            
            return redirect("cadmin_enrollment_edit", course_slug=course_slug, enrollment_id=enrollment_id)
    
    # Get some stats about this enrollment
    homework_submissions = Submission.objects.filter(enrollment=enrollment).select_related('homework').order_by('-submitted_at')
    project_submissions = ProjectSubmission.objects.filter(enrollment=enrollment).select_related('project').order_by('-submitted_at')
    
    total_homework_lip_score = sum(s.learning_in_public_score for s in homework_submissions)
    total_project_lip_score = sum(
        s.project_learning_in_public_score + s.peer_review_learning_in_public_score 
        for s in project_submissions
    )
    
    context = {
        "course": course,
        "enrollment": enrollment,
        "homework_submissions": homework_submissions,
        "homework_submissions_count": homework_submissions.count(),
        "project_submissions": project_submissions,
        "project_submissions_count": project_submissions.count(),
        "total_homework_lip_score": total_homework_lip_score,
        "total_project_lip_score": total_project_lip_score,
    }
    
    return render(request, "cadmin/enrollment_edit.html", context)
