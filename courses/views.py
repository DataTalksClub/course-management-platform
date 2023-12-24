from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone

from .models import (
    Course,
    Homework,
    Question,
    Answer,
    Submission,
    QuestionTypes,
    Enrollment,
)

from .forms import AnswerForm


def course_list(request):
    courses = Course.objects.all()
    return render(request, "courses/course_list.html", {"courses": courses})


def course_detail(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    return render(request, "courses/course_detail.html", {"course": course})


def process_question_options(question: Question, answer: Answer):
    if question.question_type == QuestionTypes.FREE_FORM.value:
        # this is text, so it's easy
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

    for option in possible_answers:
        options.append({"value": option, "is_selected": option in selected_options})

    return {"options": options}


def homework_detail(request, course_slug, homework_slug):
    course = get_object_or_404(Course, slug=course_slug)

    homework = get_object_or_404(Homework, course=course, slug=homework_slug)
    questions = Question.objects.filter(homework=homework)

    user = request.user

    if not user.is_authenticated:
        question_answers = []
        for question in questions:
            options = process_question_options(question, None)
            question_answers.append((question, options))

        context = {
            "homework": homework,
            "question_answers": question_answers,
            "is_authenticated": False,
        }

        return render(request, "homework/homework_detail.html", context)

    submission = Submission.objects \
        .filter(homework=homework, student=user) \
        .first()

    if request.method == "POST":
        answers_dict = {}
        for answer_id, answer in request.POST.lists():
            if not answer_id.startswith("answer_"):
                continue
            answers_dict[answer_id] = ",".join(answer)

        print("answers_dict", answers_dict)

        # Process the form submission
        # Create or update submission and answers
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
        answers = Answer.objects \
            .filter(submission=submission) \
            .select_related("question")
        question_answers_map = {answer.question.id: answer for answer in answers}
    else:
        question_answers_map = {}

    # Pairing questions with their answers

    question_answers = []

    for question in questions:
        answer = question_answers_map.get(question.id)
        processed_answer = process_question_options(question, answer)

        pair = (question, processed_answer)
        question_answers.append(pair)

    context = {
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

    context = {
        "enrollments": enrollments,
    }

    return render(request, "homework/leaderboard.html", context)
