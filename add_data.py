import os
import django

from datetime import datetime, timedelta


os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "course_management.settings"
)
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

# This will retrieve your 'CustomUser' model
from courses.models import (  # noqa: E402
    Course,
    Enrollment,
    Homework,
    Question,
    Submission,
    Answer,
    AnswerTypes,
    QuestionTypes,
    Project,
    ProjectSubmission,
    ReviewCriteria,
    ReviewCriteriaTypes,
    QUESTION_ANSWER_DELIMITER
)


User = get_user_model()

admin_user, created = User.objects.get_or_create(
    username="admin", defaults={"email": "alexey@datatalks.club"}
)

if created:
    admin_user.set_password("admin")
    admin_user.is_superuser = True
    admin_user.is_staff = True
    admin_user.save()


course = Course(
    title="Fake Course",
    description="This is a fake course.",
    slug="fake-course",
)
course.save()

ten_years_later = datetime.now() + timedelta(days=365 * 10)

homework1 = Homework(
    course=course,
    title="Homework 1",
    description="Description for Homework 1",
    due_date=ten_years_later,
    slug="hw1",
)
homework1.save()

admin_enrollment = Enrollment(student=admin_user, course=course)
admin_enrollment.save()


def join_possible_answers(answers: list) -> str:
    return QUESTION_ANSWER_DELIMITER.join(answers)

# Questions for Homework 1
question11 = Question(
    homework=homework1,
    text="What is 2 + 2?",
    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
    possible_answers=join_possible_answers(["3", "4", "5", "6"]),
    correct_answer="2",
)
question11.save()
question12 = Question(
    homework=homework1,
    text="Explain the theory of relativity.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.ANY.value,
    correct_answer="",
)
question12.save()
question13 = Question(
    homework=homework1,
    text="Which of these are prime numbers?",
    question_type=QuestionTypes.CHECKBOXES.value,
    possible_answers=join_possible_answers(["1", "2", "3", "4", "5"]),
    correct_answer="2,3,5",
)
question13.save()
question14 = Question(
    homework=homework1,
    text="What is the capital of France?",
    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
    possible_answers=join_possible_answers(["London", "Paris", "Berlin", "Madrid"]),
    correct_answer="2",
)
question14.save()
question15 = Question(
    homework=homework1,
    text="Calculate the area of a circle with radius 5.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.FLOAT.value,
    correct_answer="78.54",
)
question15.save()
question16 = Question(
    homework=homework1,
    text="Name a gas lighter than air.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.CONTAINS_STRING.value,
    correct_answer="Hydrogen",
)
question16.save()


admin_submission = Submission(
    homework=homework1,
    student=admin_user,
    enrollment=admin_enrollment,
)
admin_submission.save()


Answer(
    submission=admin_submission,
    student=admin_user,
    question=question11,
    answer_text="3",
).save()
Answer(
    submission=admin_submission,
    student=admin_user,
    question=question12,
    answer_text="E=mc^2",
).save()
Answer(
    submission=admin_submission,
    student=admin_user,
    question=question13,
    answer_text="2,3,4,5",
).save()
Answer(
    submission=admin_submission,
    student=admin_user,
    question=question14,
    answer_text="Paris",
).save()
Answer(
    submission=admin_submission,
    student=admin_user,
    question=question15,
    answer_text="78.54",
).save()
Answer(
    submission=admin_submission,
    student=admin_user,
    question=question16,
    answer_text="Helium",
).save()


homework2 = Homework(
    course=course,
    title="Homework 2",
    description="Description for Homework 2",
    due_date=ten_years_later,
    slug="hw2",
)
homework2.save()

# Creating questions for Homework 2
Question(
    homework=homework2,
    text="What is the boiling point of water?",
    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
    possible_answers=join_possible_answers(["50", "75", "100", "125"]),
    correct_answer="3",
).save()
Question(
    homework=homework2,
    text="Describe the process of photosynthesis.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.ANY.value,
    correct_answer="",
).save()
Question(
    homework=homework2,
    text="Select all even numbers",
    question_type=QuestionTypes.CHECKBOXES.value,
    possible_answers=join_possible_answers(["1", "2", "3", "4", "5", "6"]),
    correct_answer="2,4,6",
).save()
Question(
    homework=homework2,
    text="Who wrote Macbeth?",
    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
    possible_answers=join_possible_answers(["William Shakespeare", "Charles Dickens", "Mark Twain"]),
    correct_answer="1",
).save()
Question(
    homework=homework2,
    text="Solve for x in 2x + 3 = 11.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.INTEGER.value,
    correct_answer="4",
).save()
Question(
    homework=homework2,
    text="Name a programming language used for web development.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.CONTAINS_STRING.value,
    correct_answer="JavaScript",
).save()


project = Project(
    course=course,
    title="Fake Project",
    slug="fake-project",
    submission_due_date=ten_years_later,
    peer_review_due_date=ten_years_later,
    learning_in_public_cap_project=14,
    learning_in_public_cap_review=2,
    number_of_peers_to_evaluate=3,
    points_to_pass=10,
)

project.save()

project_submission = ProjectSubmission(
    project=project,
    student=admin_user,
    enrollment=admin_enrollment,
    github_link="https://github.com/DataTalksClub/data-engineering-zoomcamp",
    commit_id="8c45587",
    learning_in_public_links={
        "link1": "http://example.com",
        "link2": "http://example.org",
    },
    faq_contribution="Contributed to the following FAQs...",
    time_spent=10.0,
    problems_comments="This is a test submission.",
)
project_submission.save()


criteria_data = [
    {
        "description": "Problem description",
        "type": ReviewCriteriaTypes.RADIO_BUTTONS.value,
        "options": [
            {"criteria": "The problem is not described", "score": 0},
            {
                "criteria": "The problem is described but shortly or not clearly",
                "score": 1,
            },
            {
                "criteria": "The problem is well described and it's clear what the problem the project solves",
                "score": 2,
            },
        ],
    },
    {
        "description": "Cloud",
        "type": ReviewCriteriaTypes.RADIO_BUTTONS.value,
        "options": [
            {
                "criteria": "Cloud is not used, things run only locally",
                "score": 0,
            },
            {
                "criteria": "The project is developed on the cloud OR uses localstack (or similar tool) OR the project is deployed to Kubernetes or similar container management platforms",
                "score": 2,
            },
            {
                "criteria": "The project is developed on the cloud and IaC tools are used for provisioning the infrastructure",
                "score": 4,
            },
        ],
    },
    {
        "description": "Experiment tracking and model registry",
        "type": ReviewCriteriaTypes.RADIO_BUTTONS.value,
        "options": [
            {
                "criteria": "No experiment tracking or model registry",
                "score": 0,
            },
            {
                "criteria": "Experiments are tracked or models are registered in the registry",
                "score": 2,
            },
            {
                "criteria": "Both experiment tracking and model registry are used",
                "score": 4,
            },
        ],
    },
    {
        "description": "Workflow orchestration",
        "type": ReviewCriteriaTypes.RADIO_BUTTONS.value,
        "options": [
            {"criteria": "No workflow orchestration", "score": 0},
            {"criteria": "Basic workflow orchestration", "score": 2},
            {"criteria": "Fully deployed workflow", "score": 4},
        ],
    },
    {
        "description": "Model deployment",
        "type": ReviewCriteriaTypes.RADIO_BUTTONS.value,
        "options": [
            {"criteria": "Model is not deployed", "score": 0},
            {
                "criteria": "Model is deployed but only locally",
                "score": 2,
            },
            {
                "criteria": "The model deployment code is containerized and could be deployed to cloud or special tools for model deployment are used",
                "score": 4,
            },
        ],
    },
    {
        "description": "Model monitoring",
        "type": ReviewCriteriaTypes.RADIO_BUTTONS.value,
        "options": [
            {"criteria": "No model monitoring", "score": 0},
            {
                "criteria": "Basic model monitoring that calculates and reports metrics",
                "score": 2,
            },
            {
                "criteria": "Comprehensive model monitoring that sends alerts or runs a conditional workflow (e.g. retraining, generating debugging dashboard, switching to a different model) if the defined metrics threshold is violated",
                "score": 4,
            },
        ],
    },
    {
        "description": "Reproducibility",
        "type": ReviewCriteriaTypes.RADIO_BUTTONS.value,
        "options": [
            {
                "criteria": "No instructions on how to run the code at all, the data is missing",
                "score": 0,
            },
            {
                "criteria": "Some instructions are there, but they are not complete OR instructions are clear and complete, the code works, but the data is missing",
                "score": 2,
            },
            {
                "criteria": "Instructions are clear, it's easy to run the code, and it works. The versions for all the dependencies are specified",
                "score": 4,
            },
        ],
    },
    {
        "description": "Best practices",
        "type": ReviewCriteriaTypes.CHECKBOXES.value,
        "options": [
            {"criteria": "There are unit tests", "score": 1},
            {"criteria": "There is an integration test", "score": 1},
            {
                "criteria": "Linter and/or code formatter are used",
                "score": 1,
            },
            {"criteria": "There's a Makefile", "score": 1},
            {"criteria": "There are pre-commit hooks", "score": 1},
            {"criteria": "There's a CI/CD pipeline", "score": 2},
        ],
    },
]

for criterion in criteria_data:
    ReviewCriteria.objects.create(
        course=course,
        description=criterion["description"],
        review_criteria_type=criterion["type"],
        options=criterion["options"],
    )