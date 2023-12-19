import os
import django

from datetime import datetime, timedelta


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'course_management.settings')
django.setup()


from courses.models import Course, Homework, Question # noqa: E402


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
    question_type="MC",
    answer_type="INT",
    possible_answers="1,2,3,4",
    correct_answer="4",
).save()
Question(
    homework=homework1,
    text="Explain the theory of relativity.",
    question_type="FF",
    answer_type="ANY",
    correct_answer="",
).save()
Question(
    homework=homework1,
    text="Which of these are prime numbers?",
    question_type="CB",
    answer_type="CTS",
    possible_answers="2,3,4,5",
    correct_answer="2,3,5",
).save()
Question(
    homework=homework1,
    text="What is the capital of France?",
    question_type="MC",
    answer_type="EXS",
    possible_answers="London,Paris,Berlin",
    correct_answer="Paris",
).save()
Question(
    homework=homework1,
    text="Calculate the area of a circle with radius 5.",
    question_type="FF",
    answer_type="FLT",
    correct_answer="78.54",
).save()
Question(
    homework=homework1,
    text="Name a gas lighter than air.",
    question_type="FF",
    answer_type="CTS",
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
    question_type="MC",
    answer_type="INT",
    possible_answers="90,95,100,105",
    correct_answer="100",
).save()
Question(
    homework=homework2,
    text="Describe the process of photosynthesis.",
    question_type="FF",
    answer_type="ANY",
    correct_answer="",
).save()
Question(
    homework=homework2,
    text="Select all even numbers",
    question_type="CB",
    answer_type="CTS",
    possible_answers="1,2,3,4,5,6",
    correct_answer="2,4,6",
).save()
Question(
    homework=homework2,
    text="Who wrote Macbeth?",
    question_type="MC",
    answer_type="EXS",
    possible_answers="William Shakespeare,Charles Dickens,Mark Twain",
    correct_answer="William Shakespeare",
).save()
Question(
    homework=homework2,
    text="Solve for x in 2x + 3 = 11.",
    question_type="FF",
    answer_type="INT",
    correct_answer="4",
).save()
Question(
    homework=homework2,
    text="Name a programming language used for web development.",
    question_type="FF",
    answer_type="CTS",
    correct_answer="JavaScript",
).save()
