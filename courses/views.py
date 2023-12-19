from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages

from .models import Course
from .models import Homework, Question, Answer, Submission
from .models import QuestionTypes

from .forms import AnswerForm


def course_list(request):
    courses = Course.objects.all()
    return render(request, "courses/course_list.html", {"courses": courses})


def course_detail(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    return render(request, "courses/course_detail.html", {"course": course})


def process_question_options(question: Question, answer: Answer):
    # Process the answer based on question type

    if question.question_type == QuestionTypes.FREE_FORM:
        # this is text, so it's easy
        return {"text": answer.answer_text}
    
    # here we have MULTIPLE_CHOICE or CHECKBOXES
    possible_answers = question.get_possible_answers()

    # multiple options - checkbox or radio
    if not answer:
        options = possible_answers
    else:
        options = []
        selected_options = answer.answer_text.split(",")

        for option in possible_answers:
            options.append({
                'value': option,
                'is_selected': option in selected_options
            })

    return {"text": answer.answer_text, "options": options}


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

    submission = Submission.objects.filter(homework=homework, student=user).first()

    if request.method == "POST":
        answers_dict = {}
        for answer_id, answer in request.POST.lists():
            if not answer_id.startswith("answer_"):
                continue
            answers_dict[answer_id] = ",".join(answer)

        print("answers_dict", answers_dict)

        # Process the form submission
        # Create or update submission and answers
        if not submission:
            submission = Submission.objects.create(homework=homework, student=user)

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


def submit_homework(request, homework_id):
    if request.method == "POST":
        # Process the submitted answers
        # This is a simplification; you'll need to handle each question's answer
        for question in Question.objects.filter(homework_id=homework_id):
            answer_text = request.POST.get(f"answer_{question.id}")
            Answer.objects.create(
                question=question, student=request.user, answer_text=answer_text
            )
        return redirect("homework_detail", homework_id=homework_id)

    # Show the form for submission
    homework = get_object_or_404(Homework, pk=homework_id)
    return render(request, "homework/submit_homework.html", {"homework": homework})
