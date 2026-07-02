from courses.models import LeaderboardComplaint
from courses.tests.course_leaderboard_base import (
    credentials,
    CourseLeaderboardViewTestBase,
)


class CourseLeaderboardComplaintTests(CourseLeaderboardViewTestBase):
    def test_authenticated_user_can_report_leaderboard_record(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)
        self.client.login(**credentials)
        complaint_data = {
            "issue_type": LeaderboardComplaint.IssueType.HOMEWORK,
            "description": "Homework score looks incorrect.",
        }

        url = self.leaderboard_complaint_url(target)
        response = self.client.post(
            url,
            complaint_data,
        )

        redirect_url = self.leaderboard_score_breakdown_url(target)
        self.assertRedirects(
            response,
            redirect_url,
        )
        complaint = LeaderboardComplaint.objects.get(enrollment=target)
        self.assertEqual(complaint.reporter, self.user)
        self.assertEqual(
            complaint.issue_type,
            LeaderboardComplaint.IssueType.HOMEWORK,
        )

    def test_anonymous_user_is_redirected_when_reporting(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)

        url = self.leaderboard_complaint_url(target)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)
