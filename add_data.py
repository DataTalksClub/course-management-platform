import os
import django

from datetime import datetime, timedelta


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'course_management.settings')
django.setup()


from courses.models import Course, Homework, Question, AnswerTypes, QuestionTypes # noqa: E402

course = Course(
    title="Fake Course",
    description="This is a fake course.",
    slug="fake-course",
)
course.save()

ten_years_later = datetime.now() + timedelta(days=365*10)

homework1 = Homework(
    course=course,
    title="Homework 1",
    description="Description for Homework 1",
    due_date=ten_years_later,
    slug="hw1",
)
homework1.save()

# Questions for Homework 1
Question(
    homework=homework1,
    text="What is 2 + 2?",
    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
    possible_answers="1,2,3,4",
    correct_answer="4",
).save()
Question(
    homework=homework1,
    text="Explain the theory of relativity.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.ANY.value,
    correct_answer="",
).save()
Question(
    homework=homework1,
    text="Which of these are prime numbers?",
    question_type=QuestionTypes.CHECKBOXES.value,
    possible_answers="2,3,4,5",
    correct_answer="2,3,5",
).save()
Question(
    homework=homework1,
    text="What is the capital of France?",
    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
    possible_answers="London,Paris,Berlin",
    correct_answer="Paris",
).save()
Question(
    homework=homework1,
    text="Calculate the area of a circle with radius 5.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.FLOAT.value,
    correct_answer="78.54",
).save()
Question(
    homework=homework1,
    text="Name a gas lighter than air.",
    question_type=QuestionTypes.FREE_FORM.value,
    answer_type=AnswerTypes.CONTAINS_STRING.value,
    correct_answer="Hydrogen",
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
    possible_answers="90,95,100,105",
    correct_answer="100",
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
    possible_answers="1,2,3,4,5,6",
    correct_answer="2,4,6",
).save()
Question(
    homework=homework2,
    text="Who wrote Macbeth?",
    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
    possible_answers="William Shakespeare,Charles Dickens,Mark Twain",
    correct_answer="William Shakespeare",
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
