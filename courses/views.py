from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Prefetch
from django.contrib.auth.decorators import login_required


from .models import (
    Course,
    Homework,
    Question,
    Answer,
    Submission,
    QuestionTypes,
    Enrollment,
    AnswerTypes,
)

from .scoring import is_answer_correct, is_free_form_answer_correct
from .forms import AnswerForm, EnrollmentForm


def course_list(request):
    courses = Course.objects.all()
    return render(request, "courses/course_list.html", {"courses": courses})



def course_detail(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)

    user = request.user
    is_user_authenticated = user.is_authenticated

    print(f"user={user}, is_user_authenticated={is_user_authenticated}")

    if is_user_authenticated:
        submissions_prefetch = Prefetch(
            'submission_set',
            queryset=Submission.objects.filter(student=user),
            to_attr='submissions'
        )
    else:
        submissions_prefetch = Prefetch(
            'submission_set',
            queryset=Submission.objects.none(),
            to_attr='submissions'
        )

    homeworks = Homework.objects \
        .filter(course=course) \
        .prefetch_related(submissions_prefetch)

    total_score = 0

    for hw in homeworks:
        # Initialize default values
        hw.days_until_due = 0
        hw.submitted = False
        hw.score = None

        # Calculate days until deadline
        if hw.due_date > timezone.now():
            hw.days_until_due = (hw.due_date - timezone.now()).days

        print(f"hw = {hw}, hw.submissions = {hw.submissions}")

        # Check submission status and score
        if hw.submissions:
            submission = hw.submissions[0]  # Get the first (and should be only) submission

            hw.submitted = True
            if hw.is_scored:
                hw.score = submission.total_score
                total_score = total_score + submission.total_score
            else:
                hw.submitted_at = submission.submitted_at

    context = {
        'course': course,
        'homeworks': homeworks,
        'is_authenticated': is_user_authenticated,
        'total_score': total_score,
    }

    return render(request, 'courses/course_detail.html', context)


def process_question_options(homework: Homework, question: Question, answer: Answer):
    if question.question_type == QuestionTypes.FREE_FORM.value:
        # this is text, so it's easy
        if homework.is_scored:
            if not answer:
                return {"text": question.correct_answer}
            else:
                is_correct = is_free_form_answer_correct(
                    user_answer=answer.answer_text,
                    correct_answer=question.correct_answer,
                    answer_type=question.answer_type,
                )

                if is_correct:
                    correctly_selected = "option-answer-correct"
                else:
                    correctly_selected = "option-answer-incorrect"

                return {
                    "text": answer.answer_text,
                    "correctly_selected_class": correctly_selected,
                }

        if not answer:
            return {"text": ""}
        else:
            return {"text": answer.answer_text}

    # here we have MULTIPLE_CHOICE or CHECKBOXES
    options = []

    if answer:
        selected_options = answer.answer_text.split(",")
    else:
        # no answer yet, so we need to show just options
        selected_options = []

    possible_answers = question.get_possible_answers()

    if homework.is_scored:
        correct_answers = (question.correct_answer or "").split(",")

    for option in possible_answers:
        is_selected = option in selected_options
        processed_answer = {"value": option, "is_selected": is_selected}
        if homework.is_scored:
            is_correct = option in correct_answers

            correctly_selected = "option-answer-none"
            if is_selected and is_correct:
                correctly_selected = "option-answer-correct"
            if not is_selected and is_correct:
                correctly_selected = "option-answer-correct"
            if is_selected and not is_correct:
                correctly_selected = "option-answer-incorrect"

            processed_answer["correctly_selected_class"] = correctly_selected

        options.append(processed_answer)

    return {"options": options}


def homework_detail(request, course_slug, homework_slug):
    course = get_object_or_404(Course, slug=course_slug)

    homework = get_object_or_404(Homework, course=course, slug=homework_slug)
    questions = Question.objects.filter(homework=homework)

    user = request.user

    if not user.is_authenticated:
        question_answers = []
        for question in questions:
            options = process_question_options(homework, question, None)
            question_answers.append((question, options))

        context = {
            "course": course,
            "homework": homework,
            "question_answers": question_answers,
            "is_authenticated": False,
        }

        return render(request, "homework/homework_detail.html", context)

    submission = Submission.objects.filter(homework=homework, student=user).first()

    # Process the form submission
    if request.method == "POST":
        answers_dict = {}
        for answer_id, answer in request.POST.lists():
            if not answer_id.startswith("answer_"):
                continue
            answers_dict[answer_id] = ",".join(answer)

        if submission:  # submission already exists
            submission.submitted_at = timezone.now()
            submission.save()
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

            print(f"answer_{question.id}:", answer_text)
            values = {"answer_text": answer_text, "student": user}

            Answer.objects.update_or_create(
                submission=submission,
                question=question,
                defaults=values,
            )

        messages.success(
            request,
            "Thank you for submitting your homework, now your solution is saved. You can update it at any point.",
        )

        return redirect(
            "homework_detail", course_slug=course.slug, homework_slug=homework.slug
        )

    if submission:
        answers = Answer.objects.filter(submission=submission).select_related(
            "question"
        )
        question_answers_map = {answer.question.id: answer for answer in answers}
    else:
        question_answers_map = {}

    # Pairing questions with their answers

    question_answers = []

    for question in questions:
        answer = question_answers_map.get(question.id)
        processed_answer = process_question_options(homework, question, answer)

        pair = (question, processed_answer)
        question_answers.append(pair)

    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers,
        "submission": submission,
        "is_authenticated": True,
    }

    return render(request, "homework/homework_detail.html", context)


def leaderboard_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)

    enrollments = Enrollment.objects \
        .filter(course=course) \
        .order_by("-total_score")

    print(enrollments)

    context = {
        "enrollments": enrollments,
    }

    return render(request, "courses/leaderboard.html", context)


@login_required
def enrollment_detail(request, course_slug):
    enrollment = get_object_or_404(
        Enrollment,
        student=request.user,
        course__slug=course_slug
    )

    if request.method == 'POST':
        form = EnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            form.save()
            # Redirect to a success page or show a success message
            return redirect('course_detail', course_slug=course_slug)
    
    form = EnrollmentForm(instance=enrollment)

    context = {'form': form, 'course_slug': course_slug}

    return render(
        request, 
        'courses/enrollment_detail.html',
        context
    )
