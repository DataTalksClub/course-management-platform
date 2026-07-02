from dataclasses import dataclass
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    Enrollment,
    PeerReview,
    PeerReviewState,
    CriteriaResponse,
    ReviewCriteria,
    ReviewCriteriaTypes,
    ProjectState,
)


@dataclass(frozen=True)
class ExpectedCriteriaResponse:
    pair: tuple
    criteria: ReviewCriteria
    response: CriteriaResponse
    options: list[dict]


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectEvaluationTestBase(TestCase):
    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_enrollment(self, user):
        return Enrollment.objects.create(student=user, course=self.course)

    def create_project(self):
        submission_due_date = timezone.now() - timedelta(hours=1)
        peer_review_due_date = timezone.now() + timedelta(hours=1)
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.PEER_REVIEWING.value,
        )

    def create_project_submission(self, user, enrollment, github_link):
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            github_link=github_link,
            commit_id="1234567",
        )

    def create_peer_review(self):
        return PeerReview.objects.create(
            submission_under_evaluation=self.other_submission,
            reviewer=self.submission,
            optional=False,
        )

    def create_review_criteria(
        self, description, options, review_criteria_type
    ):
        return ReviewCriteria.objects.create(
            course=self.course,
            description=description,
            options=options,
            review_criteria_type=review_criteria_type,
        )

    def create_code_quality_criteria(self):
        options = [
            {"criteria": "Poor", "score": 0},
            {"criteria": "Satisfactory", "score": 1},
            {"criteria": "Good", "score": 2},
            {"criteria": "Excellent", "score": 3},
        ]
        return self.create_review_criteria(
            "Code quality",
            options,
            ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

    def create_documentation_criteria(self):
        options = [
            {"criteria": "None", "score": 0},
            {"criteria": "Basic", "score": 1},
            {"criteria": "Complete", "score": 2},
            {"criteria": "In-depth", "score": 3},
        ]
        return self.create_review_criteria(
            "Project documentation",
            options,
            ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

    def create_best_practices_criteria(self):
        options = [
            {"criteria": "Coding standards", "score": 1},
            {"criteria": "Tests", "score": 1},
            {"criteria": "Logging", "score": 1},
            {"criteria": "Version control", "score": 1},
            {"criteria": "CI/CD", "score": 1},
        ]
        return self.create_review_criteria(
            "Best practices",
            options,
            ReviewCriteriaTypes.CHECKBOXES.value,
        )

    def create_review_criteria_set(self):
        self.criteria1 = self.create_code_quality_criteria()
        self.criteria2 = self.create_documentation_criteria()
        self.criteria3 = self.create_best_practices_criteria()
        self.criteria = [self.criteria1, self.criteria2, self.criteria3]

    def create_criteria_responses(self):
        first_response = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria1,
            answer="1",
        )
        second_response = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria2,
            answer="2",
        )
        third_response = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria3,
            answer="1,3",
        )
        responses = {
            self.criteria1: first_response,
            self.criteria2: second_response,
            self.criteria3: third_response,
        }
        return responses

    def eval_submit_url(self):
        return reverse(
            "projects_eval_submit",
            args=[
                self.course.slug,
                self.project.slug,
                self.peer_review.id,
            ],
        )

    def eval_view_url(self):
        return reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

    def get_eval_submit_response(self):
        self.client.login(**credentials)
        eval_submit_url = self.eval_submit_url()
        return self.client.get(eval_submit_url)

    def review_post_data(self, **extra_fields):
        data = {
            "note_to_peer": "Well done!",
            "time_spent_reviewing": "3",
            f"answer_{self.criteria1.id}": "1",
            f"answer_{self.criteria2.id}": "2",
            f"answer_{self.criteria3.id}": "1,3",
        }
        data.update(extra_fields)
        return data

    def updated_review_post_data(self):
        updated_answers = {
            f"answer_{self.criteria1.id}": "2",
            f"answer_{self.criteria2.id}": "3",
            f"answer_{self.criteria3.id}": "1,2,3",
            "learning_in_public_links[]": [],
        }
        return self.review_post_data(**updated_answers)

    def post_eval_submit(self, post_data):
        self.client.login(**credentials)
        eval_submit_url = self.eval_submit_url()
        return self.client.post(eval_submit_url, post_data)

    def mark_peer_review_submitted(self):
        self.peer_review.state = PeerReviewState.SUBMITTED.value
        self.peer_review.save()

    def selected_options(self, rows, selected_indexes):
        options = []
        for index, row in enumerate(rows, start=1):
            criteria, score = row
            option = {
                "criteria": criteria,
                "score": score,
                "index": index,
                "is_selected": index in selected_indexes,
            }
            options.append(option)
        return options

    def assert_empty_criteria_response_pairs(self, pairs):
        self.assertEqual(len(pairs), 3)
        expected_criteria = [self.criteria1, self.criteria2, self.criteria3]
        for pair, criteria in zip(pairs, expected_criteria):
            actual_criteria, response = pair
            self.assertEqual(actual_criteria, criteria)
            self.assertIsNone(response)

    def assert_submitted_criteria_response_pairs(
        self, pairs, criteria_responses
    ):
        self.assertEqual(len(pairs), 3)
        code_quality_options = self.code_quality_options()
        code_quality_expected = ExpectedCriteriaResponse(
            pair=pairs[0],
            criteria=self.criteria1,
            response=criteria_responses[self.criteria1],
            options=code_quality_options,
        )
        documentation_options = self.documentation_options()
        documentation_expected = ExpectedCriteriaResponse(
            pair=pairs[1],
            criteria=self.criteria2,
            response=criteria_responses[self.criteria2],
            options=documentation_options,
        )
        best_practices_options = self.best_practices_options()
        best_practices_expected = ExpectedCriteriaResponse(
            pair=pairs[2],
            criteria=self.criteria3,
            response=criteria_responses[self.criteria3],
            options=best_practices_options,
        )
        for expected_row in (
            code_quality_expected,
            documentation_expected,
            best_practices_expected,
        ):
            self.assert_submitted_criteria_pair(expected_row)

    def code_quality_options(self):
        rows = [
            ("Poor", 0),
            ("Satisfactory", 1),
            ("Good", 2),
            ("Excellent", 3),
        ]
        return self.selected_options(rows, {1})

    def documentation_options(self):
        rows = [
            ("None", 0),
            ("Basic", 1),
            ("Complete", 2),
            ("In-depth", 3),
        ]
        return self.selected_options(rows, {2})

    def best_practices_options(self):
        rows = [
            ("Coding standards", 1),
            ("Tests", 1),
            ("Logging", 1),
            ("Version control", 1),
            ("CI/CD", 1),
        ]
        return self.selected_options(rows, {1, 3})

    def assert_submitted_criteria_pair(
        self,
        data: ExpectedCriteriaResponse,
    ):
        actual_criteria, actual_response = data.pair
        self.assertEqual(actual_criteria, data.criteria)
        self.assertEqual(actual_response, data.response)
        self.assertEqual(actual_criteria.options, data.options)

    def criteria_responses(self):
        return CriteriaResponse.objects.filter(review=self.peer_review)

    def assert_review_saved(self, expected_answers):
        self.peer_review = fetch_fresh(self.peer_review)
        self.assertEqual(
            self.peer_review.state, PeerReviewState.SUBMITTED.value
        )
        self.assertIsNotNone(self.peer_review.submitted_at)
        self.assertEqual(self.peer_review.note_to_peer, "Well done!")
        self.assertEqual(self.peer_review.time_spent_reviewing, 3.0)
        criteria_responses = self.criteria_responses()
        criteria_response_count = criteria_responses.count()
        self.assertEqual(criteria_response_count, len(expected_answers))
        for criteria, expected_answer in expected_answers.items():
            response = criteria_responses.get(criteria=criteria)
            self.assertEqual(response.answer, expected_answer)

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.enrollment = self.create_enrollment(self.user)
        self.project = self.create_project()
        self.submission = self.create_project_submission(
            self.user,
            self.enrollment,
            "https://github.com/user/project",
        )
        self.other_user = User.objects.create_user(
            username="student",
            email="email@email.com",
            password="12345",
        )
        self.other_enrollment = self.create_enrollment(self.other_user)
        self.other_submission = self.create_project_submission(
            self.other_user,
            self.other_enrollment,
            "https://github.com/other_student/project",
        )
        self.peer_review = self.create_peer_review()
        self.create_review_criteria_set()
