import logging

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectState,
    Enrollment,
    Homework,
    HomeworkState,
    ReviewCriteria,
    ReviewCriteriaTypes,
    ProjectEvaluationScore,
)


logger = logging.getLogger(__name__)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class CadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        # Create admin user
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        # Create review criteria for testing
        self.criteria1 = ReviewCriteria.objects.create(
            course=self.course,
            description="Problem Description",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

        self.criteria2 = ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 2},
                {"criteria": "Excellent", "score": 4},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

    def test_course_list_unauthenticated_redirects(self):
        """Test that unauthenticated users are redirected from course list"""
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_course_list_non_staff_denied(self):
        """Test that non-staff users cannot access course list"""
        self.client.login(username="test@test.com", password="12345")
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_course_list_staff_allowed(self):
        """Test that staff users can access course list"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course Administration")

    def test_course_admin_staff_allowed(self):
        """Test that staff users can access course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course.title)
        self.assertContains(response, "Admin Panel")

    def test_homework_submissions_redirect_from_courses(self):
        """Test that homework submissions view redirects to cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_project_submissions_redirect_from_courses(self):
        """Test that project submissions view redirects to cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_cadmin_homework_submissions_staff_allowed(self):
        """Test that staff users can view homework submissions in cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.homework.title)

    def test_cadmin_project_submissions_staff_allowed(self):
        """Test that staff users can view project submissions in cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.title)

    def test_project_submission_edit_get(self):
        """Test that staff users can access the project submission edit page"""
        # Create a project submission
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=6,  # 2 + 4 from criteria
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=23,  # 6 + 5 + 3 + 7 + 2
        )
        
        # Create evaluation scores for the criteria
        ProjectEvaluationScore.objects.create(
            submission=submission,
            review_criteria=self.criteria1,
            score=2,
        )
        ProjectEvaluationScore.objects.create(
            submission=submission,
            review_criteria=self.criteria2,
            score=4,
        )

        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Project Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, "Problem Description")  # criteria1
        self.assertContains(response, "Code Quality")  # criteria2
        self.assertContains(response, 'value="6"')  # project_score (readonly)
        self.assertContains(response, 'value="23"')  # total_score

    def test_project_submission_edit_post_calculates_total(self):
        """Test that editing individual criteria scores automatically calculates the total"""
        # Create a project submission
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=0,
            project_faq_score=0,
            project_learning_in_public_score=0,
            peer_review_score=0,
            peer_review_learning_in_public_score=0,
            total_score=0,
        )

        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            }
        )

        # Post new scores - now using criteria scores instead of project_score
        response = self.client.post(url, {
            f"criteria_score_{self.criteria1.id}": 2,
            f"criteria_score_{self.criteria2.id}": 4,
            "project_faq_score": 5,
            "project_learning_in_public_score": 3,
            "peer_review_score": 7,
            "peer_review_learning_in_public_score": 2,
        })

        # Should redirect back to submissions list
        self.assertEqual(response.status_code, 302)

        # Refresh submission from database
        submission.refresh_from_db()

        # Check that project_score was calculated from criteria scores (2 + 4 = 6)
        self.assertEqual(submission.project_score, 6)
        self.assertEqual(submission.project_faq_score, 5)
        self.assertEqual(submission.project_learning_in_public_score, 3)
        self.assertEqual(submission.peer_review_score, 7)
        self.assertEqual(submission.peer_review_learning_in_public_score, 2)
        # Check total: 6 + 5 + 3 + 7 + 2 = 23
        self.assertEqual(submission.total_score, 23)
        
        # Verify evaluation scores were created
        eval_scores = ProjectEvaluationScore.objects.filter(submission=submission)
        self.assertEqual(eval_scores.count(), 2)
        
        # Check individual criteria scores
        criteria1_score = ProjectEvaluationScore.objects.get(
            submission=submission,
            review_criteria=self.criteria1
        )
        self.assertEqual(criteria1_score.score, 2)
        
        criteria2_score = ProjectEvaluationScore.objects.get(
            submission=submission,
            review_criteria=self.criteria2
        )
        self.assertEqual(criteria2_score.score, 4)

    def test_project_submission_edit_post_with_checkboxes(self):
        """Test that editing submission with checkboxes works correctly"""
        # Create a project submission
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=6,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=23,
            reviewed_enough_peers=False,
            passed=False,
        )

        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            }
        )

        # Post with checkboxes checked
        response = self.client.post(url, {
            f"criteria_score_{self.criteria1.id}": 2,
            f"criteria_score_{self.criteria2.id}": 4,
            "project_faq_score": 5,
            "project_learning_in_public_score": 3,
            "peer_review_score": 7,
            "peer_review_learning_in_public_score": 2,
            "reviewed_enough_peers": "on",
            "passed": "on",
        })

        # Refresh submission from database
        submission.refresh_from_db()

        # Check that checkboxes were saved correctly
        self.assertTrue(submission.reviewed_enough_peers)
        self.assertTrue(submission.passed)

    def test_homework_score_shows_message(self):
        """Test that scoring homework shows a message on the course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_homework_score",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            }
        )
        response = self.client.post(url, follow=True)
        
        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        )
        
        # Check that a message was added
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)

    def test_project_score_shows_message(self):
        """Test that scoring project shows a message on the course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_score",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.post(url, follow=True)
        
        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        )
        
        # Check that a message was added
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)

    def test_project_assign_reviews_shows_message(self):
        """Test that assigning peer reviews shows a message on the course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_assign_reviews",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.post(url, follow=True)
        
        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        )
        
        # Check that a message was added
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)

    def test_log_as_user_requires_post_request(self):
        """Test that the log as user endpoint requires a POST request"""
        self.client.login(username="admin@test.com", password="admin123")
        
        # Try to access the endpoint with GET - should fail
        url = f"/admin/login/user/{self.user.id}/"
        response = self.client.get(url)
        
        # Should return 405 Method Not Allowed
        self.assertEqual(response.status_code, 405)

    def test_log_as_user_with_post_request(self):
        """Test that staff can log in as another user with POST request"""
        self.client.login(username="admin@test.com", password="admin123")
        
        # Create enrollment for the user
        Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        
        # Verify we're logged in as admin
        self.assertEqual(self.client.session['_auth_user_id'], str(self.admin_user.id))
        
        # Try to log in as the user with POST
        url = f"/admin/login/user/{self.user.id}/"
        response = self.client.post(url)
        
        # Should redirect to a page (the login redirect)
        self.assertEqual(response.status_code, 302)
        
        # After the POST, we should be logged in as the user
        # (The session should have changed to the target user)
        # Note: django-loginas stores the original user in a different session key
        # and switches the current user to the target user

    def test_staff_cannot_impersonate_other_staff(self):
        """Test that staff users cannot impersonate other staff users"""
        # Create another staff user
        other_staff = User.objects.create_user(
            username="staff2@test.com",
            email="staff2@test.com",
            password="staff123",
            is_staff=True,
        )
        
        self.client.login(username="admin@test.com", password="admin123")
        
        # Try to log in as another staff user with POST
        url = f"/admin/login/user/{other_staff.id}/"
        response = self.client.post(url, follow=True)
        
        # Should be redirected back with an error message
        # Check that we're still logged in as the original admin user
        self.assertEqual(response.wsgi_request.user.username, "admin@test.com")

    def test_homework_submission_edit_get(self):
        """Test that staff users can access the homework submission edit page"""
        from courses.models import Submission, Question, Answer, QuestionTypes, AnswerTypes
        
        # Create an enrollment and submission
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        
        # Create questions
        question1 = Question.objects.create(
            homework=self.homework,
            text="What is 2+2?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.INTEGER.value,
            correct_answer="4",
            scores_for_correct_answer=1,
        )
        question2 = Question.objects.create(
            homework=self.homework,
            text="What is the capital of France?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers="London\nParis\nBerlin",
            correct_answer="2",
            scores_for_correct_answer=1,
        )
        
        # Create a submission
        submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=enrollment,
            learning_in_public_links=["https://example.com/post1"],
            questions_score=2,
            faq_score=0,
            learning_in_public_score=1,
            total_score=3,
        )
        
        # Create answers
        Answer.objects.create(
            submission=submission,
            question=question1,
            answer_text="4",
            is_correct=True,
        )
        Answer.objects.create(
            submission=submission,
            question=question2,
            answer_text="2",
            is_correct=True,
        )
        
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_homework_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "submission_id": submission.id,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Homework Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, "What is 2+2?")
        self.assertContains(response, "What is the capital of France?")
        self.assertContains(response, 'value="3"')  # total_score

    def test_homework_submission_edit_post_updates_answers(self):
        """Test that editing homework answers updates the submission correctly"""
        from courses.models import Submission, Question, Answer, QuestionTypes, AnswerTypes
        
        # Create an enrollment and submission
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        
        # Create questions
        question1 = Question.objects.create(
            homework=self.homework,
            text="What is 2+2?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.INTEGER.value,
            correct_answer="4",
            scores_for_correct_answer=1,
        )
        question2 = Question.objects.create(
            homework=self.homework,
            text="What is the capital of France?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers="London\nParis\nBerlin",
            correct_answer="2",
            scores_for_correct_answer=1,
        )
        
        # Create a submission with incorrect answers
        submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=enrollment,
            learning_in_public_links=["https://example.com/post1"],
            questions_score=0,
            faq_score=0,
            learning_in_public_score=1,
            total_score=1,
        )
        
        # Create answers - initially wrong
        Answer.objects.create(
            submission=submission,
            question=question1,
            answer_text="5",  # Wrong answer
            is_correct=False,
        )
        Answer.objects.create(
            submission=submission,
            question=question2,
            answer_text="1",  # Wrong answer
            is_correct=False,
        )
        
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_homework_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "submission_id": submission.id,
            }
        )
        
        # Post updated answers
        response = self.client.post(url, {
            f"answer_{question1.id}": "4",  # Correct answer
            f"answer_{question2.id}": "2",  # Correct answer
            "learning_in_public_links": "https://example.com/post1, https://example.com/post2",
        })
        
        # Should redirect back to submissions list
        self.assertEqual(response.status_code, 302)
        
        # Refresh submission from database
        submission.refresh_from_db()
        
        # Check that the score was recalculated
        self.assertEqual(submission.questions_score, 2)  # Both questions correct now
        self.assertEqual(submission.learning_in_public_score, 2)  # Two links
        self.assertEqual(submission.total_score, 4)  # 2 + 0 + 2
        
        # Verify answers were updated
        answer1 = Answer.objects.get(submission=submission, question=question1)
        self.assertEqual(answer1.answer_text, "4")
        self.assertTrue(answer1.is_correct)
        
        answer2 = Answer.objects.get(submission=submission, question=question2)
        self.assertEqual(answer2.answer_text, "2")
        self.assertTrue(answer2.is_correct)
        
        # Verify learning in public links were updated
        self.assertEqual(len(submission.learning_in_public_links), 2)
        self.assertIn("https://example.com/post1", submission.learning_in_public_links)
        self.assertIn("https://example.com/post2", submission.learning_in_public_links)

    def test_homework_submission_edit_triggers_leaderboard_update(self):
        """Test that editing homework submission triggers leaderboard recalculation if score changes"""
        from courses.models import Submission, Question, Answer, QuestionTypes, AnswerTypes
        
        # Create an enrollment
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        
        # Create a question
        question = Question.objects.create(
            homework=self.homework,
            text="What is 2+2?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.INTEGER.value,
            correct_answer="4",
            scores_for_correct_answer=10,
        )
        
        # Create a submission with wrong answer
        submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=enrollment,
            questions_score=0,
            faq_score=0,
            learning_in_public_score=0,
            total_score=0,
        )
        
        Answer.objects.create(
            submission=submission,
            question=question,
            answer_text="5",
            is_correct=False,
        )
        
        # Set initial leaderboard position
        enrollment.total_score = 0
        enrollment.position_on_leaderboard = 999
        enrollment.save()
        
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_homework_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "submission_id": submission.id,
            }
        )
        
        # Post correct answer to change the score
        response = self.client.post(url, {
            f"answer_{question.id}": "4",  # Correct answer
            "learning_in_public_links": "",
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Refresh enrollment from database
        enrollment.refresh_from_db()
        
        # Check that leaderboard was updated (total_score should be updated)
        # The update_leaderboard function should have been called and updated the enrollment
        self.assertEqual(enrollment.total_score, 10)  # Score from the corrected answer

