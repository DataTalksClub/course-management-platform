from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from courses.models import (
    User,
    Course,
    Homework,
    Submission,
    Enrollment,
    Question,
    QuestionTypes,
    HomeworkState,
    ReviewCriteria,
    ReviewCriteriaTypes,
    Project,
    ProjectState,
    ProjectSubmission,
)

from .util import join_possible_answers

credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


class CourseDetailViewTests(TestCase):
    def setUp(self):
        # Clear cache before each test to ensure fresh state
        cache.clear()

        self.client = Client()

        self.user = User.objects.create_user(**credentials)
        self.course = Course.objects.create(
            title="Test Course", slug="test-course-2"
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user, course=self.course
        )

        # Create homeworks
        self.homework1 = Homework.objects.create(
            slug="scored-homework",
            course=self.course,
            title="Scored Homework",
            description="This homework is already scored.",
            due_date=timezone.now() - timezone.timedelta(days=1),
            state=HomeworkState.SCORED.value,
        )

        self.homework2 = Homework.objects.create(
            slug="submitted-homework",
            course=self.course,
            title="Submitted Homework",
            description="Homework with submitted answers.",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )

        self.homework3 = Homework.objects.create(
            slug="unscored-homework",
            course=self.course,
            title="Homework Without Submissions",
            description="Homework without any submissions yet.",
            due_date=timezone.now() + timezone.timedelta(days=14),
            state=HomeworkState.OPEN.value,
        )

        self.homeworks = [
            self.homework1,
            self.homework2,
            self.homework3,
        ]

        for hw in self.homeworks:
            for i in range(1, 4):
                Question.objects.create(
                    homework=hw,
                    text=f"Question {i} of {hw.title}",
                    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                    possible_answers=join_possible_answers(
                        ["A", "B", "C", "D"]
                    ),
                    correct_answer="1",
                )

        # Create submissions for the first two homeworks
        self.submission1 = Submission.objects.create(
            homework=self.homework1,
            enrollment=self.enrollment,
            student=self.user,
            total_score=80,  # Assuming this is a scored submission
        )

        self.submission2 = Submission.objects.create(
            homework=self.homework2,
            enrollment=self.enrollment,
            student=self.user,
            total_score=0,  # Assuming this is an unscored submission
        )

        # Create projects
        self.open_project = Project.objects.create(
            course=self.course,
            title="Open Project",
            slug="open-project",
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

        self.completed_project = Project.objects.create(
            course=self.course,
            title="Completed Project",
            slug="completed-project",
            state=ProjectState.COMPLETED.value,
            submission_due_date=timezone.now()
            - timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

        # Create project submissions
        self.completed_submission = ProjectSubmission.objects.create(
            project=self.completed_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            project_score=85,
        )

        self.open_submission = ProjectSubmission.objects.create(
            project=self.open_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo2",
        )

    def test_course_detail_unauthenticated_user(self):
        # Test the view for an unauthenticated user
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertTemplateUsed(response, "courses/course.html")
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertFalse(context["is_authenticated"])
        self.assertEqual(context["course"], self.course)
        self.assertEqual(len(context["homeworks"]), 3)
        self.assertIsNone(context["total_score"])

        # Check the properties of each homework in the context
        for hw in context["homeworks"]:
            self.assertIn(hw.title, [h.title for h in self.homeworks])
            self.assertFalse(hw.submitted)
            self.assertIsNone(hw.score)
            self.assertFalse(hasattr(hw, "submitted_at"))

    def test_course_detail_authenticated_user(self):
        # Test the view for an authenticated user

        total_score = 80
        self.enrollment.total_score = total_score
        self.enrollment.save()

        self.client.login(**credentials)

        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertTrue(context["is_authenticated"])
        self.assertEqual(context["course"], self.course)
        self.assertEqual(len(context["homeworks"]), 3)

        homeworks = {h.slug: h for h in response.context["homeworks"]}

        scored_homework = homeworks["scored-homework"]
        self.assertTrue(scored_homework.submitted)
        self.assertFalse(hasattr(scored_homework, "submitted_at"))
        self.assertEqual(scored_homework.is_scored(), True)
        self.assertEqual(
            scored_homework.state, HomeworkState.SCORED.value
        )
        self.assertEqual(scored_homework.score, 80)
        self.assertEqual(scored_homework.days_until_due, 0)

        submitted_homework = homeworks["submitted-homework"]
        self.assertTrue(submitted_homework.submitted)
        self.assertEqual(
            submitted_homework.state, HomeworkState.OPEN.value
        )
        self.assertEqual(
            submitted_homework.submitted_at,
            self.submission2.submitted_at,
        )
        self.assertEqual(submitted_homework.is_scored(), False)
        self.assertEqual(submitted_homework.score, None)
        self.assertEqual(submitted_homework.days_until_due, 7)

        unscored_homework = homeworks["unscored-homework"]
        self.assertFalse(unscored_homework.submitted)
        self.assertFalse(hasattr(unscored_homework, "submitted_at"))
        self.assertEqual(unscored_homework.is_scored(), False)
        self.assertEqual(unscored_homework.score, None)
        self.assertEqual(unscored_homework.days_until_due, 14)
        self.assertEqual(unscored_homework.submissions, [])

        self.assertEqual(context["total_score"], total_score)

    def test_course_detail_authenticated_user_not_enrolled(self):
        # Test the view for an authenticated user

        self.enrollment.delete()

        self.client.login(**credentials)

        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertTrue(context["is_authenticated"])
        self.assertEqual(context["course"], self.course)
        self.assertEqual(len(context["homeworks"]), 3)

        homeworks = {h.slug: h for h in response.context["homeworks"]}

        scored_homework = homeworks["scored-homework"]
        self.assertFalse(scored_homework.submitted)
        self.assertEqual(scored_homework.is_scored(), True)
        self.assertEqual(
            scored_homework.state, HomeworkState.SCORED.value
        )
        self.assertEqual(scored_homework.score, None)
        self.assertEqual(scored_homework.days_until_due, 0)

        submitted_homework = homeworks["submitted-homework"]
        self.assertFalse(submitted_homework.submitted)
        self.assertEqual(
            submitted_homework.state, HomeworkState.OPEN.value
        )
        self.assertEqual(submitted_homework.is_scored(), False)
        self.assertEqual(submitted_homework.score, None)
        self.assertEqual(submitted_homework.days_until_due, 7)

        unscored_homework = homeworks["unscored-homework"]
        self.assertFalse(unscored_homework.submitted)
        self.assertFalse(hasattr(unscored_homework, "submitted_at"))
        self.assertEqual(unscored_homework.is_scored(), False)
        self.assertEqual(unscored_homework.score, None)
        self.assertEqual(unscored_homework.days_until_due, 14)
        self.assertEqual(unscored_homework.submissions, [])

        self.assertIsNone(context["total_score"])

    def create_enrollment(
        self, name, total_score, position_on_leaderboard=None
    ):
        student = User.objects.create_user(username=name)
        enrollment = Enrollment.objects.create(
            course=self.course,
            student=student,
            display_name=name,
            total_score=total_score,
            position_on_leaderboard=position_on_leaderboard,
        )
        return enrollment

    def test_leaderboard_order(self):
        e1 = self.create_enrollment("e1", 100, 1)
        e2 = self.create_enrollment("e2", 90, 2)
        e3 = self.create_enrollment("e3", 80, 3)
        e4 = self.create_enrollment("e4", 70, 4)
        e5 = self.create_enrollment("e5", 60, 5)

        self.enrollment.total_score = 50
        self.enrollment.position_on_leaderboard = 6
        self.enrollment.save()

        self.client.login(**credentials)

        url = reverse(
            "leaderboard", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        enrollments = response.context["enrollments"]

        expected_order = [
            e1.display_name,
            e2.display_name,
            e3.display_name,
            e4.display_name,
            e5.display_name,
            self.enrollment.display_name,
        ]

        actual_order = [e['display_name'] for e in enrollments]

        self.assertEqual(actual_order, expected_order)

    def test_new_enrollment_at_the_end_of_leaderboard(self):
        e1 = self.create_enrollment("e1", 0, None)
        e2 = self.create_enrollment("e2", 90, 1)
        e3 = self.create_enrollment("e3", 80, 2)
        e4 = self.create_enrollment("e4", 70, 3)
        e5 = self.create_enrollment("e5", 0, None)

        self.enrollment.total_score = 50
        self.enrollment.position_on_leaderboard = 4
        self.enrollment.save()

        self.client.login(**credentials)

        url = reverse(
            "leaderboard", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        enrollments = response.context["enrollments"]

        expected_order = [
            e2.display_name,
            e3.display_name,
            e4.display_name,
            self.enrollment.display_name,
            # no scores, null position, order by id on tie
            e1.display_name,
            e5.display_name,
        ]

        actual_order = [e['display_name'] for e in enrollments]

        self.assertEqual(actual_order, expected_order)

        expected_positions = [1, 2, 3, 4, None, None]
        actual_positions = [
            e['position_on_leaderboard'] for e in enrollments
        ]
        self.assertEqual(actual_positions, expected_positions)

    def test_not_enrolled_yet_but_leaderboard_displays(self):
        """Test that the leaderboard displays even when user is not enrolled"""
        self.create_enrollment("e1", 100, 1)
        self.create_enrollment("e2", 90, 2)
        self.create_enrollment("e3", 80, 3)
        self.create_enrollment("e4", 70, 4)
        self.create_enrollment("e5", 60, 5)

        self.enrollment.delete()

        self.client.login(**credentials)

        url = reverse(
            "leaderboard", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Current enrollment should be None (no auto-enrollment)
        current_enrollment = response.context[
            "current_student_enrollment"
        ]
        self.assertIsNone(current_enrollment)

        # Leaderboard should still show other enrollments
        enrollments = response.context["enrollments"]
        self.assertEqual(len(enrollments), 5)

        # Verify the order is correct
        expected_order = ["e1", "e2", "e3", "e4", "e5"]
        actual_order = [e['display_name'] for e in enrollments]
        self.assertEqual(actual_order, expected_order)

    def test_not_enrolled_but_can_edit_details(self):
        self.enrollment.delete()

        self.client.login(**credentials)

        url = reverse(
            "enrollment", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        form = response.context["form"]
        enrollment = form.instance
        self.assertEqual(enrollment.student.id, self.user.id)

    def test_duplicate_course(self):
        """Test that course duplication works correctly"""
        # Create some review criteria for the original course
        review_criteria1 = ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

        review_criteria2 = ReviewCriteria.objects.create(
            course=self.course,
            description="Features Implemented",
            options=[
                {"criteria": "Basic Features", "score": 1},
                {"criteria": "Advanced Features", "score": 2},
            ],
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
        )

        # Create admin user and client
        admin_user = User.objects.create_superuser(
            username="admin@test.com",
            email="admin@test.com",
            password="admin12345",
        )
        admin_client = Client()
        admin_client.login(
            username="admin@test.com", password="admin12345"
        )

        # Get current year
        current_year = timezone.now().year

        # Set up the course with previous year in title and slug
        self.course.title = f"Test Course {current_year - 1}"
        self.course.slug = f"test-course-{current_year - 1}"
        self.course.social_media_hashtag = "#testcourse2023"
        self.course.faq_document_url = "https://example.com/faq"
        self.course.project_passing_score = 75
        self.course.save()

        # Execute the duplicate action
        url = reverse("admin:courses_course_changelist")
        data = {
            "action": "duplicate_course",
            "_selected_action": [str(self.course.pk)],
        }
        response = admin_client.post(url, data, follow=True)

        # Check if the duplication was successful
        self.assertEqual(response.status_code, 200)

        # Get the duplicated course
        new_course = Course.objects.get(
            slug=f"test-course-{current_year}"
        )

        # Test course fields
        self.assertEqual(
            new_course.title, f"Test Course {current_year}"
        )
        self.assertEqual(
            new_course.description, self.course.description
        )
        self.assertEqual(
            new_course.social_media_hashtag,
            self.course.social_media_hashtag,
        )
        self.assertEqual(
            new_course.faq_document_url, self.course.faq_document_url
        )
        self.assertEqual(
            new_course.project_passing_score, self.course.project_passing_score
        )
        self.assertFalse(new_course.first_homework_scored)
        self.assertFalse(new_course.finished)

        # Test review criteria
        new_criteria = new_course.reviewcriteria_set.all()
        self.assertEqual(new_criteria.count(), 2)

        # Check first criteria
        criteria1 = new_criteria.get(description="Code Quality")
        self.assertEqual(criteria1.options, review_criteria1.options)
        self.assertEqual(
            criteria1.review_criteria_type,
            ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

        # Check second criteria
        criteria2 = new_criteria.get(description="Features Implemented")
        self.assertEqual(criteria2.options, review_criteria2.options)
        self.assertEqual(
            criteria2.review_criteria_type,
            ReviewCriteriaTypes.CHECKBOXES.value,
        )

        # Verify that enrollments were not copied
        self.assertEqual(new_course.students.count(), 0)

    def test_course_view_with_completed_projects(self):
        """Test that the course view shows the 'See all submitted projects' button when there are completed projects"""
        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertTrue(response.context["has_completed_projects"])
        self.assertContains(response, "See all submitted projects")

    def test_course_view_without_completed_projects(self):
        """Test that the course view doesn't show the button when there are no completed projects"""
        # Change the completed project to open state
        self.completed_project.state = (
            ProjectState.COLLECTING_SUBMISSIONS.value
        )
        self.completed_project.save()

        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_completed_projects"])
        self.assertNotContains(response, "See all submitted projects")

    def test_course_view_with_certificate(self):
        """Test that the course view shows the certificate download button when a certificate is available"""
        # Set a certificate URL for the enrollment
        self.enrollment.certificate_url = "https://example.com/certificate.pdf"
        self.enrollment.save()

        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertEqual(response.context["certificate_url"], "https://example.com/certificate.pdf")
        self.assertContains(response, "Download Certificate")
        self.assertContains(response, 'href="https://example.com/certificate.pdf"')

    def test_course_view_without_certificate(self):
        """Test that the course view doesn't show the certificate download button when no certificate is available"""
        # Ensure no certificate URL is set
        self.enrollment.certificate_url = None
        self.enrollment.save()

        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertIsNone(response.context["certificate_url"])
        self.assertNotContains(response, "Download Certificate")

    def test_course_view_certificate_not_shown_when_not_authenticated(self):
        """Test that the certificate button is not shown to unauthenticated users even if certificate exists"""
        # Set a certificate URL for the enrollment
        self.enrollment.certificate_url = "https://example.com/certificate.pdf"
        self.enrollment.save()

        # Don't login - access as unauthenticated user
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        # certificate_url should be None for unauthenticated users
        self.assertIsNone(response.context["certificate_url"])
        self.assertNotContains(response, "Download Certificate")

    def test_list_all_submissions_view(self):
        """Test the list all submissions view shows submissions in correct order"""
        self.client.login(**credentials)
        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/list_all.html")

        # Check that submissions are ordered by score (completed first)
        submissions = response.context["submissions"]
        self.assertEqual(len(submissions), 2)
        self.assertEqual(submissions[0].project, self.completed_project)
        self.assertEqual(submissions[0].display_score, 85)
        self.assertEqual(submissions[1].project, self.open_project)
        self.assertEqual(submissions[1].display_score, -1)

    def test_list_all_submissions_view_unauthorized(self):
        """Test that unauthorized users can access the submissions list"""
        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )
        self.assertEqual(response.status_code, 200)  # see as usual

    def test_submissions_display_format(self):
        """Test that submissions are displayed with correct format and N/A for unevaluated"""
        self.client.login(**credentials)
        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )
        self.assertEqual(response.status_code, 200)

        submissions = response.context["submissions"]
        our_submissions = {}

        for submission in submissions:
            if submission.enrollment.student == self.user:
                our_submissions[submission.project_id] = submission

        self.assertEqual(len(our_submissions), 2)

        evaluated_submission = our_submissions[
            self.completed_project.id
        ]
        self.assertEqual(
            evaluated_submission.project, self.completed_project
        )
        self.assertEqual(evaluated_submission.display_score, 85)
        self.assertEqual(
            evaluated_submission.enrollment.student, self.user
        )

        open_submission = our_submissions[self.open_project.id]
        self.assertEqual(open_submission.project, self.open_project)
        self.assertEqual(open_submission.display_score, -1)
        self.assertEqual(open_submission.enrollment.student, self.user)

    def test_homeworks_sorted_by_due_date(self):
        """Test that homeworks are displayed in order of due date."""
        # Create homeworks with different due dates in non-chronological order
        homework_late = Homework.objects.create(
            slug="homework-late",
            course=self.course,
            title="Late Homework",
            description="Homework due later",
            due_date=timezone.now() + timezone.timedelta(days=30),
            state=HomeworkState.OPEN.value,
        )
        
        homework_early = Homework.objects.create(
            slug="homework-early", 
            course=self.course,
            title="Early Homework",
            description="Homework due earlier",
            due_date=timezone.now() + timezone.timedelta(days=5),
            state=HomeworkState.OPEN.value,
        )
        
        homework_middle = Homework.objects.create(
            slug="homework-middle",
            course=self.course, 
            title="Middle Homework",
            description="Homework due in the middle",
            due_date=timezone.now() + timezone.timedelta(days=15),
            state=HomeworkState.OPEN.value,
        )
        
        # Add questions to each homework
        for hw in [homework_late, homework_early, homework_middle]:
            Question.objects.create(
                homework=hw,
                text=f"Question for {hw.title}",
                question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                possible_answers=join_possible_answers(["A", "B", "C"]),
                correct_answer="1",
            )
        
        # Test as unauthenticated user
        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Get homeworks from context
        homeworks = response.context["homeworks"]
        
        # Verify we have all homeworks (original 3 + new 3)
        self.assertEqual(len(homeworks), 6)
        
        # Check that homeworks are sorted by due_date
        # The first homework should be the one with the earliest due date
        # among the new homeworks we created
        homework_slugs = [hw.slug for hw in homeworks]
        
        # Find the positions of our new homeworks in the sorted list
        early_pos = homework_slugs.index("homework-early")
        middle_pos = homework_slugs.index("homework-middle") 
        late_pos = homework_slugs.index("homework-late")
        
        # Verify they are in chronological order (early < middle < late)
        self.assertLess(early_pos, middle_pos)
        self.assertLess(middle_pos, late_pos)
        
        # Test as authenticated user
        self.client.login(**credentials)
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        homeworks = response.context["homeworks"]
        
        # Verify the same ordering for authenticated users
        homework_slugs = [hw.slug for hw in homeworks]
        early_pos = homework_slugs.index("homework-early")
        middle_pos = homework_slugs.index("homework-middle")
        late_pos = homework_slugs.index("homework-late")
        
        self.assertLess(early_pos, middle_pos)
        self.assertLess(middle_pos, late_pos)

    def test_course_visibility_in_list(self):
        """Test that non-visible courses don't appear in the course list"""
        # Create a visible course
        visible_course = Course.objects.create(
            title="Visible Course",
            slug="visible-course",
            visible=True
        )
        
        # Create a non-visible course
        hidden_course = Course.objects.create(
            title="Hidden Course",
            slug="hidden-course",
            visible=False
        )
        
        # Test the course list view
        url = reverse("course_list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that visible course is in the list
        active_courses = response.context["active_courses"]
        finished_courses = response.context["finished_courses"]
        all_courses = list(active_courses) + list(finished_courses)
        course_slugs = [course.slug for course in all_courses]
        
        self.assertIn("visible-course", course_slugs)
        self.assertNotIn("hidden-course", course_slugs)
    
    def test_hidden_course_accessible_via_direct_link(self):
        """Test that non-visible courses are still accessible via direct link"""
        # Create a non-visible course
        hidden_course = Course.objects.create(
            title="Hidden Course",
            slug="hidden-course",
            visible=False
        )
        
        # Test direct access to the course
        url = reverse("course", kwargs={"course_slug": "hidden-course"})
        response = self.client.get(url)
        
        # Should be accessible
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["course"], hidden_course)
    
    def test_duplicate_course_preserves_visibility(self):
        """Test that course duplication preserves the visibility setting"""
        current_year = timezone.now().year
        previous_year = current_year - 1
        
        # Set the course to be hidden with previous year in slug
        self.course.visible = False
        self.course.title = f"Test Course {previous_year}"
        self.course.slug = f"test-course-{previous_year}"
        self.course.save()
        
        # Create admin user and client
        admin_user = User.objects.create_superuser(
            username="admin2@test.com",
            email="admin2@test.com",
            password="admin12345",
        )
        admin_client = Client()
        admin_client.login(
            username="admin2@test.com", password="admin12345"
        )
        
        # Execute the duplicate action
        url = reverse("admin:courses_course_changelist")
        data = {
            "action": "duplicate_course",
            "_selected_action": [str(self.course.pk)],
        }
        response = admin_client.post(url, data, follow=True)
        
        # Check if the duplication was successful
        self.assertEqual(response.status_code, 200)
        
        # Get the duplicated course
        new_course = Course.objects.get(
            slug=f"test-course-{current_year}"
        )
        
        # Test that visibility was preserved
        self.assertFalse(new_course.visible)

    def test_project_deadline_display_for_peer_review_state(self):
        """Test that the correct deadline is shown based on submission status when project is in PR state"""
        # Create a project in peer review state
        pr_project = Project.objects.create(
            course=self.course,
            title="Peer Review Project",
            slug="pr-project",
            state=ProjectState.PEER_REVIEWING.value,
            submission_due_date=timezone.now() - timezone.timedelta(days=1),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=7),
        )

        # Create another user who submitted the project
        user_with_submission = User.objects.create_user(
            username="submitted@test.com",
            email="submitted@test.com",
            password="12345"
        )
        enrollment_with_submission = Enrollment.objects.create(
            student=user_with_submission,
            course=self.course
        )
        ProjectSubmission.objects.create(
            project=pr_project,
            student=user_with_submission,
            enrollment=enrollment_with_submission,
            github_link="https://github.com/test/pr-repo",
        )

        # Test 1: Unauthenticated user should see submission deadline
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        # Should show submission deadline date
        submission_deadline_str = pr_project.submission_due_date.strftime('%Y-%m-%d')
        self.assertIn(submission_deadline_str, content)

        # Test 2: Authenticated user WITHOUT submission should see submission deadline
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        # Should show submission deadline for the PR project
        submission_deadline_str = pr_project.submission_due_date.strftime('%Y-%m-%d')
        self.assertIn(submission_deadline_str, content)

        # Test 3: Authenticated user WITH submission should see peer review deadline
        self.client.logout()
        self.client.login(username="submitted@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        # Should show peer review deadline
        peer_review_deadline_str = pr_project.peer_review_due_date.strftime('%Y-%m-%d')
        self.assertIn(peer_review_deadline_str, content)

    def test_course_view_does_not_auto_enroll(self):
        """Test that visiting the course page does not auto-enroll a user"""
        # Delete the existing enrollment
        self.enrollment.delete()

        # Verify enrollment is deleted
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0)

        # Login and visit the course page
        self.client.login(**credentials)
        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Verify NO enrollment was created
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0,
                        "Course view should not auto-enroll users")

    def test_leaderboard_view_does_not_auto_enroll(self):
        """Test that visiting the leaderboard page does not auto-enroll a user"""
        # Create some other users' enrollments
        self.create_enrollment("e1", 100, 1)
        self.create_enrollment("e2", 90, 2)

        # Delete the existing enrollment
        self.enrollment.delete()

        # Verify enrollment is deleted
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0)

        # Login and visit the leaderboard page
        self.client.login(**credentials)
        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Verify NO enrollment was created
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0,
                        "Leaderboard view should not auto-enroll users")

        # Verify the context shows None for current enrollment
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNone(current_enrollment,
                         "Current student enrollment should be None when not enrolled")

    def test_leaderboard_unauthenticated_user(self):
        """Test leaderboard for unauthenticated users"""
        # Create some enrollments for the leaderboard
        self.create_enrollment("Alice", 100, 1)
        self.create_enrollment("Bob", 90, 2)
        self.create_enrollment("Charlie", 80, 3)

        # Logout and visit leaderboard without authentication
        self.client.logout()

        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Context checks
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNone(current_enrollment)
        current_enrollment_id = response.context.get("current_student_enrollment_id")
        self.assertIsNone(current_enrollment_id)

        enrollments = response.context["enrollments"]
        self.assertEqual(len(enrollments), 4)  # Alice, Bob, Charlie, and self.enrollment

        # HTML content checks - should NOT show "Your Record" section
        self.assertNotContains(response, "Your Record")
        self.assertNotContains(response, "Your total score")
        self.assertNotContains(response, "Display name")
        self.assertNotContains(response, "Jump to your record")

        # Should show the leaderboard with other students
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertContains(response, "Charlie")

    def test_leaderboard_authenticated_without_enrollment(self):
        """Test leaderboard for authenticated users who are not enrolled"""
        # Create some enrollments for the leaderboard
        self.create_enrollment("Alice", 100, 1)
        self.create_enrollment("Bob", 90, 2)
        self.create_enrollment("Charlie", 80, 3)

        # Delete the test user's enrollment
        self.enrollment.delete()

        # Login and visit leaderboard
        self.client.login(**credentials)

        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Context checks
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNone(current_enrollment)
        current_enrollment_id = response.context.get("current_student_enrollment_id")
        self.assertIsNone(current_enrollment_id)

        enrollments = response.context["enrollments"]
        self.assertEqual(len(enrollments), 3)  # Only Alice, Bob, Charlie

        # HTML content checks - should NOT show "Your Record" section
        self.assertNotContains(response, "Your Record")
        self.assertNotContains(response, "Your total score")
        self.assertNotContains(response, "Display name")
        self.assertNotContains(response, "Jump to your record")

        # Should show the leaderboard with other students
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertContains(response, "Charlie")

    def test_leaderboard_authenticated_with_enrollment(self):
        """Test leaderboard for authenticated users who are enrolled"""
        # Create some other enrollments
        e1 = self.create_enrollment("Alice", 100, 1)
        e2 = self.create_enrollment("Bob", 90, 2)
        e3 = self.create_enrollment("Charlie", 80, 3)

        # Set up test user's enrollment
        self.enrollment.display_name = "TestUser"
        self.enrollment.total_score = 95
        self.enrollment.position_on_leaderboard = 2
        self.enrollment.save()

        # Login and visit leaderboard
        self.client.login(**credentials)

        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Context checks
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNotNone(current_enrollment)
        self.assertEqual(current_enrollment.id, self.enrollment.id)
        self.assertEqual(current_enrollment.display_name, "TestUser")
        self.assertEqual(current_enrollment.total_score, 95)

        current_enrollment_id = response.context.get("current_student_enrollment_id")
        self.assertEqual(current_enrollment_id, self.enrollment.id)

        enrollments = response.context["enrollments"]
        self.assertEqual(len(enrollments), 4)  # Alice, TestUser, Bob, Charlie

        # HTML content checks - should show "Your Record" section
        self.assertContains(response, "Your Record")
        self.assertContains(response, "Your total score: 95")
        self.assertContains(response, "Position: 2")
        self.assertContains(response, "Display name: TestUser")
        self.assertContains(response, "Jump to your record")
        self.assertContains(response, f"record-{self.enrollment.id}")

        # Should show the leaderboard with all students
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertContains(response, "Charlie")
        self.assertContains(response, "TestUser")

