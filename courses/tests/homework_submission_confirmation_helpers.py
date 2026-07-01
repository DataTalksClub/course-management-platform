from courses.models import QuestionTypes


class HomeworkSubmissionConfirmationMixin:
    def confirmation_post_data(self):
        return {
            f"answer_{self.multiple_choice_question.id}": ["2"],
            f"answer_{self.free_form_question.id}": [
                "I used pandas and DuckDB."
            ],
            f"answer_{self.checkbox_question.id}": ["1", "3"],
            "learning_in_public_links[]": ["https://example.com/post"],
            "time_spent_lectures": "2.5",
            "time_spent_homework": "4",
            "problems_comments": "No blockers.",
            "faq_contribution_url": (
                "https://github.com/DataTalksClub/faq/pull/1"
            ),
        }

    def datamailer_preference_post_data(self):
        answer_key = f"answer_{self.multiple_choice_question.id}"
        return {
            answer_key: ["2"],
            "learning_in_public_links[]": [],
        }

    def public_base_url_post_data(self):
        answer_key = f"answer_{self.multiple_choice_question.id}"
        return {
            answer_key: ["1"],
            "learning_in_public_links[]": [],
        }

    def assert_confirmation_payload_basics(self, payload, submission):
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(
            payload["template_key"],
            "homework-submission-confirmation",
        )
        self.assertEqual(payload["category_tag"], "submission-results")
        self.assertEqual(
            payload["idempotency_key"],
            (
                f"homework-submission:{submission.id}:"
                f"{submission.submitted_at.isoformat()}"
            ),
        )
        self.assertEqual(
            payload["metadata"]["event"],
            "homework_submission",
        )

    def assert_confirmation_context(self, payload, submission):
        context = payload["context"]
        self.assertEqual(context["submission_id"], submission.id)
        self.assertEqual(
            context["update_url"],
            "http://localhost/course/homework/hw1",
        )
        self.assertEqual(
            context["profile_url"],
            "http://localhost/accounts/settings/",
        )
        self.assertEqual(
            context["notification_category"],
            "homework and project submissions",
        )
        self.assertIn(
            "homework and project submission emails",
            context["notification_footer_text"],
        )
        self.assertEqual(
            context["intro_text"],
            "Your homework submission for Homework 1 in Course was saved.",
        )

    def expected_learning_in_public_field(self):
        return {
            "key": "learning_in_public_links",
            "label": "Learning in public links",
            "value": "https://example.com/post",
            "values": ["https://example.com/post"],
        }

    def expected_lecture_time_field(self):
        return {
            "key": "time_spent_lectures",
            "label": "Time spent on lectures",
            "value": "2.5 hours",
        }

    def expected_homework_time_field(self):
        return {
            "key": "time_spent_homework",
            "label": "Time spent on homework",
            "value": "4 hours",
        }

    def expected_problem_comments_field(self):
        return {
            "key": "problems_comments",
            "label": "Problems, comments, or feedback",
            "value": "No blockers.",
        }

    def expected_faq_contribution_field(self):
        return {
            "key": "faq_contribution_url",
            "label": "FAQ contribution URL",
            "value": "https://github.com/DataTalksClub/faq/pull/1",
        }

    def expected_submission_fields(self):
        fields = []
        field = self.expected_learning_in_public_field()
        fields.append(field)
        field = self.expected_lecture_time_field()
        fields.append(field)
        field = self.expected_homework_time_field()
        fields.append(field)
        field = self.expected_problem_comments_field()
        fields.append(field)
        field = self.expected_faq_contribution_field()
        fields.append(field)
        return fields

    def assert_submission_fields(self, payload):
        expected_fields = self.expected_submission_fields()
        self.assertEqual(
            payload["context"]["submission_fields"],
            expected_fields,
        )

    def multiple_choice_answer_record(self):
        selected_options = []
        option = {"index": 2, "value": "Second option"}
        selected_options.append(option)
        return {
            "question_id": self.multiple_choice_question.id,
            "question": "Pick one option",
            "question_type": QuestionTypes.MULTIPLE_CHOICE.value,
            "answer": "2. Second option",
            "raw_answer": "2",
            "selected_options": selected_options,
        }

    def free_form_answer_record(self):
        return {
            "question_id": self.free_form_question.id,
            "question": "Explain your approach",
            "question_type": QuestionTypes.FREE_FORM.value,
            "answer": "I used pandas and DuckDB.",
            "raw_answer": "I used pandas and DuckDB.",
            "selected_options": [],
        }

    def checkbox_answer_record(self):
        selected_options = []
        option = {"index": 1, "value": "Alpha"}
        selected_options.append(option)
        option = {"index": 3, "value": "Gamma"}
        selected_options.append(option)
        return {
            "question_id": self.checkbox_question.id,
            "question": "Pick all matching options",
            "question_type": QuestionTypes.CHECKBOXES.value,
            "answer": "1. Alpha, 3. Gamma",
            "raw_answer": "1,3",
            "selected_options": selected_options,
        }

    def submitted_answer_records(self):
        records = []
        record = self.multiple_choice_answer_record()
        records.append(record)
        record = self.free_form_answer_record()
        records.append(record)
        record = self.checkbox_answer_record()
        records.append(record)
        return records

    def assert_submitted_answers(self, payload):
        expected_answers = self.submitted_answer_records()
        self.assertEqual(
            payload["context"]["submitted_answers"],
            expected_answers,
        )

    def assert_confirmation_summary(self, payload):
        self.assertIn(
            "Time spent on lectures: 2.5 hours",
            payload["context"]["submission_summary_text"],
        )
        self.assertIn(
            "Pick all matching options: 1. Alpha, 3. Gamma",
            payload["context"]["submitted_answers_text"],
        )
