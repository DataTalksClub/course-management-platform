import logging
from dataclasses import dataclass

from django.urls import reverse
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

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
    ProjectVote,
)


logger = logging.getLogger(__name__)


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


class ProjectEvaluationTestCase(TestCase):
    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_enrollment(self, user):
        return Enrollment.objects.create(student=user, course=self.course)

    def create_project(self):
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() - timedelta(hours=1),
            peer_review_due_date=timezone.now() + timedelta(hours=1),
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

    def create_review_criteria_set(self):
        self.criteria1 = self.create_review_criteria(
            "Code quality",
            [
                {"criteria": "Poor", "score": 0},
                {"criteria": "Satisfactory", "score": 1},
                {"criteria": "Good", "score": 2},
                {"criteria": "Excellent", "score": 3},
            ],
            ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )
        self.criteria2 = self.create_review_criteria(
            "Project documentation",
            [
                {"criteria": "None", "score": 0},
                {"criteria": "Basic", "score": 1},
                {"criteria": "Complete", "score": 2},
                {"criteria": "In-depth", "score": 3},
            ],
            ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )
        self.criteria3 = self.create_review_criteria(
            "Best practices",
            [
                {"criteria": "Coding standards", "score": 1},
                {"criteria": "Tests", "score": 1},
                {"criteria": "Logging", "score": 1},
                {"criteria": "Version control", "score": 1},
                {"criteria": "CI/CD", "score": 1},
            ],
            ReviewCriteriaTypes.CHECKBOXES.value,
        )
        self.criteria = [self.criteria1, self.criteria2, self.criteria3]

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
        return self.client.get(self.eval_submit_url())

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
        return self.review_post_data(
            **{
                f"answer_{self.criteria1.id}": "2",
                f"answer_{self.criteria2.id}": "3",
                f"answer_{self.criteria3.id}": "1,2,3",
                "learning_in_public_links[]": [],
            }
        )

    def post_eval_submit(self, post_data):
        self.client.login(**credentials)
        return self.client.post(self.eval_submit_url(), post_data)

    def create_criteria_responses(self):
        responses = {
            self.criteria1: CriteriaResponse.objects.create(
                review=self.peer_review,
                criteria=self.criteria1,
                answer="1",
            ),
            self.criteria2: CriteriaResponse.objects.create(
                review=self.peer_review,
                criteria=self.criteria2,
                answer="2",
            ),
            self.criteria3: CriteriaResponse.objects.create(
                review=self.peer_review,
                criteria=self.criteria3,
                answer="1,3",
            ),
        }
        return responses

    def mark_peer_review_submitted(self):
        self.peer_review.state = PeerReviewState.SUBMITTED.value
        self.peer_review.save()

    def selected_options(self, rows, selected_indexes):
        options = []
        for index, (criteria, score) in enumerate(rows, start=1):
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
        code_quality_expected = ExpectedCriteriaResponse(
            pair=pairs[0],
            criteria=self.criteria1,
            response=criteria_responses[self.criteria1],
            options=self.code_quality_options(),
        )
        documentation_expected = ExpectedCriteriaResponse(
            pair=pairs[1],
            criteria=self.criteria2,
            response=criteria_responses[self.criteria2],
            options=self.documentation_options(),
        )
        best_practices_expected = ExpectedCriteriaResponse(
            pair=pairs[2],
            criteria=self.criteria3,
            response=criteria_responses[self.criteria3],
            options=self.best_practices_options(),
        )
        expected_rows = [
            code_quality_expected,
            documentation_expected,
            best_practices_expected,
        ]
        for expected_row in expected_rows:
            self.assert_submitted_criteria_pair(expected_row)

    def code_quality_options(self):
        return self.selected_options(
            [
                ("Poor", 0),
                ("Satisfactory", 1),
                ("Good", 2),
                ("Excellent", 3),
            ],
            {1},
        )

    def documentation_options(self):
        return self.selected_options(
            [
                ("None", 0),
                ("Basic", 1),
                ("Complete", 2),
                ("In-depth", 3),
            ],
            {2},
        )

    def best_practices_options(self):
        return self.selected_options(
            [
                ("Coding standards", 1),
                ("Tests", 1),
                ("Logging", 1),
                ("Version control", 1),
                ("CI/CD", 1),
            ],
            {1, 3},
        )

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
        self.assertEqual(criteria_responses.count(), len(expected_answers))
        for criteria, expected_answer in expected_answers.items():
            response = criteria_responses.get(criteria=criteria)
            self.assertEqual(response.answer, expected_answer)

    def test_eval_submit_not_authenticated(self):
        response = self.client.get(self.eval_submit_url())
        self.assertEqual(response.status_code, 302)

    def test_eval_submit_get_authenticated_not_submitted_accepting_responses(
        self,
    ):
        response = self.get_eval_submit_response()
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertTrue(context["accepting_submissions"])
        self.assertFalse(context["disabled"])

        course = context["course"]
        self.assertEqual(course, self.course)

        project = context["project"]
        self.assertEqual(project, self.project)

        review = context["review"]
        self.assertEqual(review, self.peer_review)
        self.assertEqual(review.state, PeerReviewState.TO_REVIEW.value)

        submission = context["submission"]
        self.assertEqual(
            submission, self.peer_review.submission_under_evaluation
        )

        self.assert_empty_criteria_response_pairs(
            context["criteria_response_pairs"]
        )

        submission = context["submission"]
        self.assertEqual(
            submission, self.peer_review.submission_under_evaluation
        )

    def test_eval_submit_get_authenticated_not_submitted_not_accepting_responses(
        self,
    ):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        response = self.get_eval_submit_response()
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Peer review form is closed.",
            status_code=200,
        )
        self.assertNotContains(
            response,
            'id="submit-button"',
            status_code=200,
        )

        context = response.context

        self.assertFalse(context["accepting_submissions"])
        self.assertTrue(context["disabled"])

        review = context["review"]
        self.assertEqual(review, self.peer_review)

        self.assert_empty_criteria_response_pairs(
            context["criteria_response_pairs"]
        )

    def test_eval_submit_post_not_accepting_responses(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        response = self.post_eval_submit(self.review_post_data())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Peer review form is closed.",
            status_code=200,
        )

        self.peer_review = fetch_fresh(self.peer_review)
        self.assertEqual(self.peer_review.state, PeerReviewState.TO_REVIEW.value)
        self.assertEqual(self.peer_review.note_to_peer, "")
        self.assertIsNone(self.peer_review.submitted_at)
        self.assertFalse(
            CriteriaResponse.objects.filter(review=self.peer_review).exists()
        )

    def test_eval_submit_get_authenticated_submitted(self):
        criteria_responses = self.create_criteria_responses()
        self.mark_peer_review_submitted()

        response = self.get_eval_submit_response()
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertTrue(context["accepting_submissions"])

        review = context["review"]
        self.assertEqual(review, self.peer_review)
        self.assertEqual(review.state, PeerReviewState.SUBMITTED.value)

        self.assert_submitted_criteria_response_pairs(
            context["criteria_response_pairs"],
            criteria_responses,
        )

    def test_eval_submit_post_not_submitted(self):
        criteria_responses = self.criteria_responses()
        self.assertEqual(criteria_responses.count(), 0)

        response = self.post_eval_submit(
            self.review_post_data(
                **{
                    "learning_in_public_links[]": [
                        "http://example.com/page",
                        "http://example.com/page2",
                    ],
                },
                problems_comments="No problems",
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assert_review_saved(
            {
                self.criteria1: "1",
                self.criteria2: "2",
                self.criteria3: "1,3",
            }
        )
        self.assertEqual(self.peer_review.problems_comments, "No problems")

        learning_in_public_links = (
            self.peer_review.learning_in_public_links
        )

        self.assertEqual(len(learning_in_public_links), 2)
        self.assertEqual(
            learning_in_public_links[0],
            "http://example.com/page",
        )
        self.assertEqual(
            learning_in_public_links[1],
            "http://example.com/page2",
        )

    def test_eval_submit_post_already_submitted(self):
        criteria_response_map = self.create_criteria_responses()
        self.mark_peer_review_submitted()
        criteria_responses = self.criteria_responses()
        self.assertEqual(criteria_responses.count(), 3)

        response = self.post_eval_submit(self.updated_review_post_data())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(criteria_responses.count(), 3)

        c1 = fetch_fresh(criteria_response_map[self.criteria1])
        self.assertEqual(c1.answer, "2")

        c2 = fetch_fresh(criteria_response_map[self.criteria2])
        self.assertEqual(c2.answer, "3")

        c3 = fetch_fresh(criteria_response_map[self.criteria3])
        self.assertEqual(c3.answer, "1,2,3")

    def test_eval_view_authenticated_no_submission(self):
        """Test that eval view offers voluntary reviews without submission."""
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

        self.submission.delete()

        self.client.login(**credentials)

        url = reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/eval.html")
        
        self.assertFalse(response.context["has_submission"])
        
        self.assertContains(
            response,
            "you can still volunteer to evaluate submissions",
            status_code=200,
        )
        self.assertNotContains(
            response,
            "Review progress",
            status_code=200,
        )

    def test_eval_view_shows_optional_reviews_without_submission(self):
        """Voluntary reviewers see selected optional reviews on eval page."""
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()
        self.submission.delete()
        volunteer_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/example/volunteer",
            commit_id="abcdef1",
            volunteer_review_only=True,
        )
        PeerReview.objects.create(
            submission_under_evaluation=self.other_submission,
            reviewer=volunteer_submission,
            note_to_peer="",
            optional=True,
        )

        self.client.login(**credentials)
        response = self.client.get(
            reverse(
                "projects_eval",
                args=[self.course.slug, self.project.slug],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_submission"])
        self.assertContains(response, "Selected reviews")
        self.assertContains(
            response,
            "these reviews are for practice and feedback",
        )
        self.assertContains(response, self.other_enrollment.display_name)
        self.assertNotContains(response, "Review progress")

    def test_eval_view_authenticated_with_submission(self):
        """Test that eval view shows reviews when user has submitted their project"""
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

        self.client.login(**credentials)

        url = reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/eval.html")
        
        self.assertTrue(response.context["has_submission"])
        
        self.assertNotContains(
            response,
            "you did not submit your project",
            status_code=200,
        )
        self.assertContains(
            response,
            "Evaluate",
            status_code=200,
        )

    def test_eval_view_separates_assigned_and_selected_reviews(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()
        PeerReview.objects.create(
            submission_under_evaluation=self.other_submission,
            reviewer=self.submission,
            note_to_peer="",
            optional=True,
        )

        self.client.login(**credentials)
        response = self.client.get(
            reverse(
                "projects_eval",
                args=[self.course.slug, self.project.slug],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review progress")
        self.assertContains(response, "Selected reviews")
        self.assertEqual(len(response.context["assigned_reviews"]), 1)
        self.assertEqual(len(response.context["selected_reviews"]), 1)

    def test_eval_submit_page_can_vote_for_reviewed_submission(self):
        self.client.login(**credentials)

        url = reverse(
            "projects_eval_submit",
            args=[self.course.slug, self.project.slug, self.peer_review.id],
        )
        response = self.client.post(
            url,
            {
                "form_action": "vote",
                "submission_id": self.other_submission.id,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ProjectVote.objects.filter(
                voter=self.user,
                submission=self.other_submission,
            ).exists()
        )

    def test_eval_view_shows_closed_message_when_project_is_not_peer_reviewing(self):
        """Test that eval view stays on page with closed peer-review message."""
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        self.client.login(**credentials)

        url = reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/eval.html")
        self.assertContains(
            response,
            "Peer review form is closed.",
            status_code=200,
        )
        self.assertNotContains(
            response,
            "Review progress",
            status_code=200,
        )

    def test_eval_view_shows_no_submission_closed_message_when_completed(self):
        """Test direct eval URL explains why non-submitters cannot evaluate."""
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()
        self.submission.delete()

        self.client.login(**credentials)

        url = reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/eval.html")
        self.assertContains(
            response,
            "submission window is closed",
            status_code=200,
        )
        self.assertNotContains(
            response,
            "Submission details",
            status_code=200,
        )

    def test_list_view_authenticated_no_submission(self):
        """Test that list view allows voluntary evaluation without submission."""
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

        self.submission.delete()

        self.client.login(**credentials)

        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/list.html")
        
        self.assertFalse(response.context["has_submission"])
        self.assertContains(
            response,
            'aria-label="Add to evaluation"',
            status_code=200,
        )
        self.assertNotContains(response, "Other submissions")

    def test_list_view_authenticated_with_submission(self):
        """Test that list view shows Add to Evaluation button when user has submitted their project"""
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

        self.peer_review.delete()

        self.client.login(**credentials)

        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/list.html")
        
        self.assertTrue(response.context["has_submission"])
        self.assertContains(
            response,
            'aria-label="Add to evaluation"',
            status_code=200,
        )

    def test_project_list_links_student_to_repository(self):
        """Project list links student names to repositories and leaderboard stays linked."""
        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                "leaderboard_score_breakdown",
                kwargs={
                    "course_slug": self.course.slug,
                    "enrollment_id": self.enrollment.id,
                },
            ),
        )
        self.assertContains(response, self.submission.github_link)
        self.assertContains(response, 'aria-label="Open repository"')
        self.assertContains(
            response,
            reverse("list_all_project_submissions", args=[self.course.slug]),
        )

    def test_project_list_view_is_paginated(self):
        """Test that the project submissions list limits results per page."""
        for index in range(30):
            user = User.objects.create_user(
                username=f"student-{index}",
                email=f"student-{index}@example.com",
                password="12345",
            )
            enrollment = Enrollment.objects.create(
                student=user,
                course=self.course,
                display_name=f"Student {index}",
            )
            ProjectSubmission.objects.create(
                project=self.project,
                student=user,
                enrollment=enrollment,
                github_link=f"https://github.com/student-{index}/project",
                commit_id="1234567",
            )

        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["submissions_page"].paginator.count, 32)
        self.assertEqual(len(response.context["submissions"]), 25)
        self.assertTrue(response.context["submissions_page"].has_next())
