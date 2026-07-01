from courses.models import Enrollment
from courses.tests.course_leaderboard_base import (
    credentials,
    CourseLeaderboardViewTestBase,
)


class CourseLeaderboardViewTests(CourseLeaderboardViewTestBase):

    def test_leaderboard_order(self):
        e1 = self.create_leaderboard_enrollment("e1", 100, 1)
        e2 = self.create_leaderboard_enrollment("e2", 90, 2)
        e3 = self.create_leaderboard_enrollment("e3", 80, 3)
        e4 = self.create_leaderboard_enrollment("e4", 70, 4)
        e5 = self.create_leaderboard_enrollment("e5", 60, 5)
        self.set_current_enrollment_leaderboard_position(50, 6)
        self.client.login(**credentials)

        url = self.leaderboard_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        expected_order = [
            e1.display_name,
            e2.display_name,
            e3.display_name,
            e4.display_name,
            e5.display_name,
            self.enrollment.display_name,
        ]
        self.assert_leaderboard_order(response, expected_order)

    def test_new_enrollment_at_the_end_of_leaderboard(self):
        enrollments = self.create_new_enrollment_leaderboard()
        self.set_current_enrollment_leaderboard_position(50, 4)

        response = self.leaderboard_response(login=True)

        self.assertEqual(response.status_code, 200)
        expected_order = [
            enrollments["e2"].display_name,
            enrollments["e3"].display_name,
            enrollments["e4"].display_name,
            self.enrollment.display_name,
            enrollments["e1"].display_name,
            enrollments["e5"].display_name,
        ]
        self.assert_leaderboard_order(response, expected_order)
        expected_positions = [1, 2, 3, 4, None, None]
        self.assert_leaderboard_positions(response, expected_positions)

    def test_not_enrolled_yet_but_leaderboard_displays(self):
        self.create_leaderboard_enrollment("e1", 100, 1)
        self.create_leaderboard_enrollment("e2", 90, 2)
        self.create_leaderboard_enrollment("e3", 80, 3)
        self.create_leaderboard_enrollment("e4", 70, 4)
        self.create_leaderboard_enrollment("e5", 60, 5)
        self.enrollment.delete()
        self.client.login(**credentials)

        url = self.leaderboard_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        current_enrollment = response.context["current_student_enrollment"]
        self.assertIsNone(current_enrollment)

    def test_leaderboard_view_does_not_auto_enroll(self):
        self.create_leaderboard_enrollment("e1", 100, 1)
        self.create_leaderboard_enrollment("e2", 90, 2)
        self.enrollment.delete()
        self.client.login(**credentials)

        url = self.leaderboard_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
        ).count()
        self.assertEqual(enrollment_count, 0)
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNone(current_enrollment)

    def test_leaderboard_unauthenticated_user(self):
        self.create_standard_leaderboard()
        self.client.logout()

        url = self.leaderboard_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assert_no_current_enrollment_context(response)
        enrollments = response.context["enrollments"]
        enrollment_count = len(enrollments)
        self.assertEqual(enrollment_count, 4)
        self.assert_no_current_record_visible(response)
        self.assert_leaderboard_names_visible(response)

    def test_leaderboard_authenticated_without_enrollment(self):
        self.create_standard_leaderboard()
        self.enrollment.delete()
        self.client.login(**credentials)

        url = self.leaderboard_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assert_no_current_enrollment_context(response)
        enrollments = response.context["enrollments"]
        enrollment_count = len(enrollments)
        self.assertEqual(enrollment_count, 3)
        self.assert_no_current_record_visible(response)
        self.assert_leaderboard_names_visible(response)

    def test_leaderboard_authenticated_with_enrollment(self):
        self.create_standard_leaderboard()
        self.enrollment.display_name = "TestUser"
        self.enrollment.total_score = 95
        self.enrollment.position_on_leaderboard = 2
        self.enrollment.save()

        response = self.leaderboard_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assert_current_student_enrollment(response)
        enrollments = response.context["enrollments"]
        enrollment_count = len(enrollments)
        self.assertEqual(enrollment_count, 4)
        self.assert_current_student_record_visible(response)
        self.assert_standard_leaderboard_visible(response)
        self.assertContains(response, "TestUser")
