from courses.models import QuestionTypes


def confirmation_post_data(test_case):
    return {
        f"answer_{test_case.multiple_choice_question.id}": ["2"],
        f"answer_{test_case.free_form_question.id}": [
            "I used pandas and DuckDB."
        ],
        f"answer_{test_case.checkbox_question.id}": ["1", "3"],
        "learning_in_public_links[]": ["https://example.com/post"],
        "time_spent_lectures": "2.5",
        "time_spent_homework": "4",
        "problems_comments": "No blockers.",
        "faq_contribution_url": (
            "https://github.com/DataTalksClub/faq/pull/1"
        ),
    }


def datamailer_preference_post_data(test_case):
    answer_key = f"answer_{test_case.multiple_choice_question.id}"
    return {
        answer_key: ["2"],
        "learning_in_public_links[]": [],
    }


def public_base_url_post_data(test_case):
    answer_key = f"answer_{test_case.multiple_choice_question.id}"
    return {
        answer_key: ["1"],
        "learning_in_public_links[]": [],
    }


def assert_confirmation_payload_basics(test_case, payload, submission):
    test_case.assertEqual(payload["email"], "student@example.com")
    test_case.assertEqual(
        payload["template_key"],
        "homework-submission-confirmation",
    )
    test_case.assertEqual(payload["category_tag"], "submission-results")
    test_case.assertEqual(
        payload["idempotency_key"],
        (
            f"homework-submission:{submission.id}:"
            f"{submission.submitted_at.isoformat()}"
        ),
    )
    test_case.assertEqual(
        payload["metadata"]["event"],
        "homework_submission",
    )


def assert_confirmation_context(test_case, payload, submission):
    context = payload["context"]
    test_case.assertEqual(context["submission_id"], submission.id)
    test_case.assertEqual(
        context["update_url"],
        "http://localhost/course/homework/hw1",
    )
    test_case.assertEqual(
        context["profile_url"],
        "http://localhost/accounts/settings/",
    )
    test_case.assertEqual(
        context["notification_category"],
        "homework and project submissions",
    )
    test_case.assertIn(
        "homework and project submission emails",
        context["notification_footer_text"],
    )
    test_case.assertEqual(
        context["intro_text"],
        "Your homework submission for Homework 1 in Course was saved.",
    )


def assert_confirmation_summary(test_case, payload):
    test_case.assertIn(
        "Time spent on lectures: 2.5 hours",
        payload["context"]["submission_summary_text"],
    )
    test_case.assertIn(
        "Pick all matching options: 1. Alpha, 3. Gamma",
        payload["context"]["submitted_answers_text"],
    )


def expected_learning_in_public_field():
    return {
        "key": "learning_in_public_links",
        "label": "Learning in public links",
        "value": "https://example.com/post",
        "values": ["https://example.com/post"],
    }


def expected_lecture_time_field():
    return {
        "key": "time_spent_lectures",
        "label": "Time spent on lectures",
        "value": "2.5 hours",
    }


def expected_homework_time_field():
    return {
        "key": "time_spent_homework",
        "label": "Time spent on homework",
        "value": "4 hours",
    }


def expected_problem_comments_field():
    return {
        "key": "problems_comments",
        "label": "Problems, comments, or feedback",
        "value": "No blockers.",
    }


def expected_faq_contribution_field():
    return {
        "key": "faq_contribution_url",
        "label": "FAQ contribution URL",
        "value": "https://github.com/DataTalksClub/faq/pull/1",
    }


def expected_submission_fields():
    fields = []
    field = expected_learning_in_public_field()
    fields.append(field)
    field = expected_lecture_time_field()
    fields.append(field)
    field = expected_homework_time_field()
    fields.append(field)
    field = expected_problem_comments_field()
    fields.append(field)
    field = expected_faq_contribution_field()
    fields.append(field)
    return fields


def assert_submission_fields(test_case, payload):
    expected_fields = expected_submission_fields()
    test_case.assertEqual(
        payload["context"]["submission_fields"],
        expected_fields,
    )


def multiple_choice_answer_record(test_case):
    selected_options = []
    option = {"index": 2, "value": "Second option"}
    selected_options.append(option)
    return {
        "question_id": test_case.multiple_choice_question.id,
        "question": "Pick one option",
        "question_type": QuestionTypes.MULTIPLE_CHOICE.value,
        "answer": "2. Second option",
        "raw_answer": "2",
        "selected_options": selected_options,
    }


def free_form_answer_record(test_case):
    return {
        "question_id": test_case.free_form_question.id,
        "question": "Explain your approach",
        "question_type": QuestionTypes.FREE_FORM.value,
        "answer": "I used pandas and DuckDB.",
        "raw_answer": "I used pandas and DuckDB.",
        "selected_options": [],
    }


def checkbox_answer_record(test_case):
    selected_options = []
    option = {"index": 1, "value": "Alpha"}
    selected_options.append(option)
    option = {"index": 3, "value": "Gamma"}
    selected_options.append(option)
    return {
        "question_id": test_case.checkbox_question.id,
        "question": "Pick all matching options",
        "question_type": QuestionTypes.CHECKBOXES.value,
        "answer": "1. Alpha, 3. Gamma",
        "raw_answer": "1,3",
        "selected_options": selected_options,
    }


def submitted_answer_records(test_case):
    records = []
    record = multiple_choice_answer_record(test_case)
    records.append(record)
    record = free_form_answer_record(test_case)
    records.append(record)
    record = checkbox_answer_record(test_case)
    records.append(record)
    return records


def assert_submitted_answers(test_case, payload):
    expected_answers = submitted_answer_records(test_case)
    test_case.assertEqual(
        payload["context"]["submitted_answers"],
        expected_answers,
    )
