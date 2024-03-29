# Generated by Django 4.2.10 on 2024-02-11 16:11
import logging

from django.db import migrations

from courses.models import Answer, QuestionTypes

logger = logging.getLogger("courses.migrations")


def replace_answers_with_indexes(possible_answers, answers, question_id=None):
    possible_answers = [
        answer.strip().lower() for answer in possible_answers
    ]
    answers = answers.lower().strip()

    logger.debug(f"Possible answers: {possible_answers}")
    logger.debug(f"User answers: {answers}")

    correct_indexes = []

    for answer in answers.split(","):
        answer = answer.strip()
        try:
            zero_based_index = possible_answers.index(answer)
            index = zero_based_index + 1
            correct_indexes.append(str(index))
        except ValueError:
            logger.error(
                f"Answer '{answer}' not found in possible_answers for question ID {question_id}"
            )

    result = ",".join(correct_indexes)
    logger.debug(f"Corrected result: {result}")
    return result


def update_answers_with_indexes(apps, schema_editor):
    updated_answers = []

    for answer in Answer.objects.all():
        question = answer.question
        if question.question_type not in [
            QuestionTypes.MULTIPLE_CHOICE.value,
            QuestionTypes.CHECKBOXES.value,
        ]:
            continue

        if question.possible_answers and answer.answer_text:
            possible_answers = question.get_possible_answers()

            updated_answer = replace_answers_with_indexes(
                possible_answers, answer.answer_text, question.id
            )

            answer.answer_text = updated_answer
            updated_answers.append(answer)

            logger.debug(
                f"Updated answer ID {answer.id} with index/indices: {updated_answer}"
            )

    Answer.objects.bulk_update(updated_answers, ["answer_text"])


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0004_update_correct_answer_indexes"),
    ]

    operations = [
        migrations.RunPython(update_answers_with_indexes),
    ]
