from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectState,
    ProjectSubmission,
)
from courses.tests.course_list_base import CourseListViewTestBase
from courses.views.course_homepage import submitted_project_ids_for_user

User = get_user_model()


class CourseListPeerReviewAssignmentTest(CourseListViewTestBase):
    def create_peer_review_course(self, state):
        course = Course.objects.create(
            title="Peer Review Course",
            slug="peer-review-course",
            description="Course with a single project.",
        )
        project = Project.objects.create(
            course=course,
            title="Course Project",
            slug="course-project",
            state=state,
            submission_due_date=timezone.now() - timezone.timedelta(days=1),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=7),
        )
        return course, project

    def create_student(self):
        student = User.objects.create_user(
            username="peer-review-student",
            email="peer-review-student@test.com",
            password="test-password",
        )
        self.client.force_login(student)
        return student

    def submit_project(self, project, student):
        enrollment, _ = Enrollment.objects.get_or_create(
            student=student,
            course=project.course,
        )
        return ProjectSubmission.objects.create(
            project=project,
            student=student,
            enrollment=enrollment,
            github_link="https://github.com/test/project",
            commit_id="0123456789abcdef0123456789abcdef01234567",
        )

    def course_page_response(self, course):
        course_url = self.course_url(course)
        return self.client.get(course_url)

    def course_url(self, course):
        return reverse("course", kwargs={"course_slug": course.slug})

    def test_peer_review_hidden_while_collecting_submissions(self):
        course, _ = self.create_peer_review_course(
            ProjectState.COLLECTING_SUBMISSIONS.value
        )

        response = self.course_list_response()

        course_card = self.course_card_for(response, course)
        self.assertNotIn("Peer review", course_card)
        self.assertIn("Project: Course Project", course_card)

    def test_peer_review_hidden_while_project_is_closed(self):
        course, _ = self.create_peer_review_course(
            ProjectState.CLOSED.value
        )

        response = self.course_list_response()

        course_card = self.course_card_for(response, course)
        self.assertNotIn("Peer review", course_card)
        self.assertIn("Project: Course Project", course_card)

    def test_peer_review_shown_when_peer_reviewing(self):
        course, _ = self.create_peer_review_course(
            ProjectState.PEER_REVIEWING.value
        )

        response = self.course_list_response()

        course_card = self.course_card_for(response, course)
        self.assertIn("Peer review: Course Project", course_card)

    def test_peer_review_hidden_for_student_without_submission(self):
        course, _ = self.create_peer_review_course(
            ProjectState.PEER_REVIEWING.value
        )
        self.create_student()

        response = self.course_list_response()

        course_card = self.course_card_for(response, course)
        self.assertNotIn("Peer review", course_card)
        self.assertIn("Project: Course Project", course_card)

    def test_peer_review_shown_for_student_with_submission(self):
        course, project = self.create_peer_review_course(
            ProjectState.PEER_REVIEWING.value
        )
        student = self.create_student()
        self.submit_project(project, student)

        response = self.course_list_response()

        course_card = self.course_card_for(response, course)
        self.assertIn("Peer review: Course Project", course_card)

    def test_peer_review_remains_visible_after_project_completion(self):
        course, project = self.create_peer_review_course(
            ProjectState.COMPLETED.value
        )
        student = self.create_student()
        self.submit_project(project, student)

        response = self.course_list_response()

        course_card = self.course_card_for(response, course)
        self.assertIn("Peer review: Course Project", course_card)

    def test_course_page_context_hides_peer_review_without_submission(self):
        course, _ = self.create_peer_review_course(
            ProjectState.PEER_REVIEWING.value
        )
        self.create_student()

        response = self.course_page_response(course)

        assignment = response.context["course"].home_current_assignment
        self.assertEqual(assignment["label"], "Project")

    def test_course_page_context_shows_peer_review_after_submission(self):
        course, project = self.create_peer_review_course(
            ProjectState.PEER_REVIEWING.value
        )
        student = self.create_student()
        self.submit_project(project, student)

        response = self.course_page_response(course)

        assignment = response.context["course"].home_current_assignment
        self.assertEqual(assignment["label"], "Peer review")

    def test_submission_lookup_batches_courses_in_one_query(self):
        course, project = self.create_peer_review_course(
            ProjectState.PEER_REVIEWING.value
        )
        other_project = Project.objects.get(
            course=self.course,
            slug="completed-project",
        )
        student = self.create_student()
        self.submit_project(project, student)
        self.submit_project(other_project, student)

        with self.assertNumQueries(1):
            submitted_ids = submitted_project_ids_for_user(
                [course, self.course],
                student,
            )

        self.assertEqual(submitted_ids, {project.id, other_project.id})
