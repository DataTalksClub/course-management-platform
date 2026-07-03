from .serializer_counts import annotated_or_count


def question_to_dict(question):
    answers_count = annotated_or_count(
        question, "answer_count", "answer_set"
    )
    possible_answers = question.get_possible_answers()
    delete_blockers = []
    if answers_count:
        delete_blockers.append("has_answers")
    return {
        "id": question.id,
        "text": question.text,
        "question_type": question.question_type,
        "answer_type": question.answer_type,
        "possible_answers": possible_answers,
        "correct_answer": question.correct_answer,
        "scores_for_correct_answer": question.scores_for_correct_answer,
        "answers_count": answers_count,
        "can_delete": answers_count == 0,
        "delete_blockers": delete_blockers,
    }
