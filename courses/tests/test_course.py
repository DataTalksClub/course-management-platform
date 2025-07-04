from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

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

        actual_order = [e.display_name for e in enrollments]

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

        actual_order = [e.display_name for e in enrollments]

        self.assertEqual(actual_order, expected_order)

        expected_positions = [1, 2, 3, 4, None, None]
        actual_positions = [
            e.position_on_leaderboard for e in enrollments
        ]
        self.assertEqual(actual_positions, expected_positions)

    def test_not_enrolled_yet_but_leaderboard_displays(self):
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

        current_enrollment = response.context[
            "current_student_enrollment"
        ]
        self.assertEqual(current_enrollment.student.id, self.user.id)
        self.assertEqual(current_enrollment.total_score, 0)
        self.assertIsNone(current_enrollment.position_on_leaderboard)

        enrollments = response.context["enrollments"]
        last_enrollment = enrollments[len(enrollments) - 1]
        self.assertEqual(last_enrollment.id, current_enrollment.id)

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

