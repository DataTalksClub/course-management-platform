import logging

from typing import List, Optional
from urllib.parse import urlparse

from django.http import HttpRequest, HttpResponse

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Prefetch

from django.contrib.auth.decorators import login_required

from django.core.exceptions import ValidationError

from .models import (
    Course,
    Homework,
    Question,
    Answer,
    Submission,
    QuestionTypes,
    Enrollment,
    Project,
    ProjectSubmission,
    ProjectState,
    PeerReview,
    User,
)

from .scoring import is_free_form_answer_correct
from .forms import EnrollmentForm

logger = logging.getLogger(__name__)


NONE_LIST = [None]


def ping(request):
    return HttpResponse("OK")


def course_list(request):
    courses = Course.objects.all()
    return render(
        request, "courses/course_list.html", {"courses": courses}
    )


def get_projects_for_course(
    course: Course, user: User
) -> List[Project]:
    if user.is_authenticated:
        queryset = ProjectSubmission.objects.filter(student=user)
    else:
        queryset = ProjectSubmission.objects.none()

    submissions_prefetch = Prefetch(
        "projectsubmission_set",
        queryset=queryset,
        to_attr="submissions",
    )

    projects = Project.objects.filter(course=course).prefetch_related(
        submissions_prefetch
    )

    for project in projects:
        update_project_with_additional_info(project)

    return list(projects)


def update_project_with_additional_info(project: Project) -> None:
    days_until_due = 0

    if project.state == ProjectState.COLLECTING_SUBMISSIONS.value:
        if project.submission_due_date > timezone.now():
            days_until_due = (
                project.submission_due_date - timezone.now()
            ).days

        project.days_until_due = days_until_due
        project.submitted = False
        project.score = None
    elif project.state == ProjectState.COLLECTING_SUBMISSIONS.value:
        pass
    elif project.state == ProjectState.COMPLETED.value:
        pass
    else:
        # log unknown state
        pass

    if not project.submissions:
        return

    submission = project.submissions[0]
    project.submitted = True

    if project.state == ProjectState.COMPLETED.value:
        pass
        # project.score = submission.total_score
    else:
        project.submitted_at = submission.submitted_at


def course_view(request: HttpRequest, course_slug: str) -> HttpResponse:
    course = get_object_or_404(Course, slug=course_slug)

    user = request.user
    homeworks = get_homeworks_for_course(course, user)

    homework_score = sum(hw.score or 0 for hw in homeworks)
    total_score = homework_score

    projects = get_projects_for_course(course, user)

    context = {
        "course": course,
        "homeworks": homeworks,
        "projects": projects,
        "is_authenticated": user.is_authenticated,
        "total_score": total_score,
    }

    return render(request, "courses/course.html", context)


def get_homeworks_for_course(course: Course, user) -> List[Homework]:
    if user.is_authenticated:
        queryset = Submission.objects.filter(student=user)
    else:
        queryset = Submission.objects.none()

    submissions_prefetch = Prefetch(
        "submission_set", queryset=queryset, to_attr="submissions"
    )

    homeworks = Homework.objects.filter(course=course).prefetch_related(
        submissions_prefetch
    )

    for hw in homeworks:
        update_homework_with_additional_info(hw)

    return list(homeworks)


def update_homework_with_additional_info(homework: Homework) -> None:
    days_until_due = 0

    if homework.due_date > timezone.now():
        days_until_due = (homework.due_date - timezone.now()).days + 1

    homework.days_until_due = days_until_due
    homework.submitted = False
    homework.score = None

    if not homework.submissions:
        return

    submission = homework.submissions[0]

    homework.submitted = True
    if homework.is_scored:
        homework.score = submission.total_score
    else:
        homework.submitted_at = submission.submitted_at


def process_quesion_free_form(
    homework: Homework, question: Question, answer: Answer
):
    if not homework.is_scored:
        if not answer:
            return {"text": ""}
        else:
            return {"text": answer.answer_text}

    if not answer:
        return {"text": question.correct_answer}

    # the homework is scored and we want to show the answers

    is_correct = is_free_form_answer_correct(question, answer)

    if is_correct:
        correctly_selected = "option-answer-correct"
    else:
        correctly_selected = "option-answer-incorrect"

    return {
        "text": answer.answer_text,
        "correctly_selected_class": correctly_selected,
    }


def process_question_options_multiple_choice_or_checkboxes(
    homework: Homework, question: Question, answer: Optional[Answer]
):
    options = []

    if answer:
        selected_options = extract_selected_options(answer)
    else:
        # no answer yet, so we need to show just options
        selected_options = []

    possible_answers = question.get_possible_answers()

    if homework.is_scored:
        correct_indices = question.get_correct_answer_indices()

    for zero_based_index, option in enumerate(possible_answers):
        index = zero_based_index + 1
        is_selected = index in selected_options

        processed_answer = {
            "value": option,
            "is_selected": is_selected,
            "index": index,
        }

        if homework.is_scored:
            is_correct = index in correct_indices

            correctly_selected = determine_answer_class(
                is_selected, is_correct
            )

            processed_answer[
                "correctly_selected_class"
            ] = correctly_selected

        options.append(processed_answer)

    return {"options": options}


def extract_selected_options(answer):
    if not answer:
        return []

    answer_text = answer.answer_text or ""
    answer_text = answer_text.strip()

    if not answer_text:
        return []

    selected_options = answer_text.strip().split(",")

    result = []

    for option in selected_options:
        option = option.strip()
        if not option:
            continue
        try:
            result.append(int(option))
        except ValueError:
            pass

    return result


def determine_answer_class(is_selected: bool, is_correct: bool) -> str:
    if is_selected and is_correct:
        return "option-answer-correct"
    if not is_selected and is_correct:
        return "option-answer-correct"
    if is_selected and not is_correct:
        return "option-answer-incorrect"
    return "option-answer-none"


def process_question_options(
    homework: Homework, question: Question, answer: Answer
):
    if question.question_type == QuestionTypes.FREE_FORM.value:
        return process_quesion_free_form(homework, question, answer)

    return process_question_options_multiple_choice_or_checkboxes(
        homework, question, answer
    )


def tryparsefloat(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def clean_learning_in_public_links(
    links: List[str], cap: int
) -> List[str]:
    cleaned_links = []

    for link in links:
        if len(link) == 0:
            continue
        if link in cleaned_links:
            continue
        if len(cleaned_links) >= cap:
            break

        cleaned_links.append(link)

    return cleaned_links


def process_homework_submission(
    request: HttpRequest,
    course: Course,
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
):
    user = request.user

    answers_dict = {}
    for answer_id, answer in request.POST.lists():
        if not answer_id.startswith("answer_"):
            continue
        answer = [a.strip() for a in answer]
        answers_dict[answer_id] = ",".join(answer)

    if submission:
        submission.submitted_at = timezone.now()
    else:
        enrollment, _ = Enrollment.objects.get_or_create(
            student=user,
            course=course,
        )
        submission = Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
        )

    for question in questions:
        answer_text = answers_dict.get(f"answer_{question.id}")

        values = {"answer_text": answer_text}

        Answer.objects.update_or_create(
            submission=submission,
            question=question,
            defaults=values,
        )

    if homework.homework_url_field:
        submission.homework_link = request.POST.get("homework_url")

    if homework.learning_in_public_cap > 0:
        links = request.POST.getlist("learning_in_public_links[]")
        cleaned_links = clean_learning_in_public_links(
            links, homework.learning_in_public_cap
        )
        submission.learning_in_public_links = cleaned_links

    if homework.time_spent_lectures_field:
        time_spent_lectures = request.POST.get("time_spent_lectures")
        if (
            time_spent_lectures is not None
            and time_spent_lectures != ""
        ):
            submission.time_spent_lectures = float(time_spent_lectures)

    if homework.time_spent_homework_field:
        time_spent_homework = request.POST.get("time_spent_homework")
        if (
            time_spent_homework is not None
            and time_spent_homework != ""
        ):
            submission.time_spent_homework = float(time_spent_homework)

    if homework.problems_comments_field:
        problems_comments = request.POST.get("problems_comments", "")
        submission.problems_comments = problems_comments.strip()

    if homework.faq_contribution_field:
        faq_contribution = request.POST.get("faq_contribution", "")
        submission.faq_contribution = faq_contribution.strip()

    submission.save()

    messages.success(
        request,
        "Thank you for submitting your homework, now your solution is saved. You can update it at any point.",
        extra_tags="homework",
    )

    return redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )


def homework_detail_build_context_not_authenticated(
    course: Course,
    homework: Homework,
    questions: List[Question],
) -> dict:
    question_answers = []
    for question in questions:
        options = process_question_options(homework, question, None)
        question_answers.append((question, options))

    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers,
        "is_authenticated": False,
        "disabled": True,
    }

    return context


def homework_detail_build_context_authenticated(
    course: Course,
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
) -> dict:
    if submission:
        answers = Answer.objects.filter(
            submission=submission
        ).select_related("question")

        question_answers_map = {
            answer.question.id: answer for answer in answers
        }
    else:
        question_answers_map = {}

    # Pairing questions with their answers

    question_answers = []

    for question in questions:
        answer = question_answers_map.get(question.id)
        processed_answer = process_question_options(
            homework, question, answer
        )

        pair = (question, processed_answer)
        question_answers.append(pair)

    disabled = homework.is_scored

    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers,
        "submission": submission,
        "is_authenticated": True,
        "disabled": disabled,
        "accepting_submissions": not homework.is_scored,
    }

    return context


def homework_view(
    request: HttpRequest, course_slug: str, homework_slug: str
):
    course = get_object_or_404(Course, slug=course_slug)

    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )
    questions = Question.objects.filter(homework=homework).order_by(
        "id"
    )

    user = request.user

    if not user.is_authenticated:
        context = homework_detail_build_context_not_authenticated(
            course=course, homework=homework, questions=questions
        )
        return render(request, "homework/homework.html", context)

    submission = Submission.objects.filter(
        homework=homework, student=user
    ).first()

    logger.info(f"submission={submission}")

    # Process the form submission
    if request.method == "POST":
        return process_homework_submission(
            request=request,
            course=course,
            homework=homework,
            questions=questions,
            submission=submission,
        )

    context = homework_detail_build_context_authenticated(
        course=course,
        homework=homework,
        questions=questions,
        submission=submission,
    )

    return render(request, "homework/homework.html", context)


def leaderboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)

    user = request.user
    current_student_enrollment = None
    current_student_enrollment_id = None

    if user.is_authenticated:
        current_student_enrollment = get_object_or_404(
            Enrollment, student=request.user, course__slug=course_slug
        )
        current_student_enrollment_id = current_student_enrollment.id

    enrollments = Enrollment.objects.filter(course=course).order_by(
        "position_on_leaderboard"
    )

    context = {
        "enrollments": enrollments,
        "course": course,
        "current_student_enrollment": current_student_enrollment,
        "current_student_enrollment_id": current_student_enrollment_id,
    }

    return render(request, "courses/leaderboard.html", context)


def leaderboard_score_breakdown_view(
    request, course_slug: str, enrollment_id: int
):
    # course = get_object_or_404(Course, slug=course_slug)
    # Get the specific enrollment
    enrollment = get_object_or_404(
        Enrollment, id=enrollment_id, course__slug=course_slug
    )

    # Get submissions related to the enrollment
    submissions = Submission.objects.filter(
        enrollment=enrollment
    ).order_by("-homework__is_scored", "homework__id")

    context = {
        "enrollment": enrollment,
        "submissions": submissions,
    }

    return render(
        request, "courses/leaderboard_score_breakdown.html", context
    )


@login_required
def enrollment_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)

    enrollment = get_object_or_404(
        Enrollment, student=request.user, course__slug=course_slug
    )

    if request.method == "POST":
        form = EnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            form.save()
            return redirect("course", course_slug=course_slug)
        else:
            messages.error(
                request,
                "There was an error updating your enrollment",
                extra_tags="homework",
            )
            return redirect("enrollment", course_slug=course_slug)
            # TODO: add POST to form below

    form = EnrollmentForm(instance=enrollment)

    context = {"form": form, "course": course}

    return render(request, "courses/enrollment.html", context)


def project_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    user = request.user
    is_authenticated = user.is_authenticated

    enrollment = None
    project_submission = None

    if is_authenticated:
        project_submission = ProjectSubmission.objects.filter(
            project=project, student=request.user
        ).first()

        if project_submission:
            enrollment = project_submission.enrollment

    accepting_submissions = (
        project.state == ProjectState.COLLECTING_SUBMISSIONS.value
    )

    if request.method == "POST":
        if project_submission:
            project_submission.submitted_at = timezone.now()
        else:
            enrollment, _ = Enrollment.objects.get_or_create(
                student=user,
                course=course,
            )
            project_submission = ProjectSubmission.objects.create(
                project=project,
                student=user,
                enrollment=enrollment,
            )

        project_submission.github_link = request.POST.get("github_link")
        project_submission.commit_id = request.POST.get("commit_id")

        if project.learning_in_public_cap_project > 0:
            links = request.POST.getlist("learning_in_public_links[]")
            cleaned_links = clean_learning_in_public_links(
                links, project.learning_in_public_cap_project
            )
            project_submission.learning_in_public_links = cleaned_links

        if project.time_spent_project_field:
            time_spent = request.POST.get("time_spent")
            if time_spent is not None and time_spent != "":
                project_submission.time_spent = tryparsefloat(
                    time_spent
                )

        if project.problems_comments_field:
            problems_comments = request.POST.get(
                "problems_comments", ""
            )
            project_submission.problems_comments = (
                problems_comments.strip()
            )

        if project.faq_contribution_field:
            faq_contribution = request.POST.get("faq_contribution", "")
            project_submission.faq_contribution = (
                faq_contribution.strip()
            )

        project_submission.save()

        messages.success(
            request,
            "Thank you for submitting your homework, now your solution is saved. You can update it at any point.",
            extra_tags="homework",
        )

        return redirect(
            "project",
            course_slug=course.slug,
            project_slug=project.slug,
        )

    disabled = not accepting_submissions

    context = {
        "course": course,
        "project": project,
        "submission": project_submission,
        "is_authenticated": is_authenticated,
        "disabled": disabled,
        "accepting_submissions": accepting_submissions,
    }

    return render(request, "projects/project.html", context)


@login_required
def projects_eval_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    student_submissions = ProjectSubmission.objects.filter(
        project=project, student=request.user
    )

    reviews = PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    )

    context = {
        "course": course,
        "project": project,
        "reviews": reviews,
    }

    return render(request, "projects/eval.html", context)
