from courses.models import ProjectSubmission, User

from .project_list_view_base import ProjectListViewTestBase


class ProjectListPaginationViewTests(ProjectListViewTestBase):
    def create_paginated_submissions(self):
        for index in range(30):
            user = User.objects.create_user(
                username=f"student-{index}",
                email=f"student-{index}@example.com",
                password="12345",
            )
            display_name = f"Student {index}"
            enrollment = self.create_enrollment(user, display_name)
            github_link = f"https://github.com/student-{index}/project"
            ProjectSubmission.objects.create(
                project=self.project,
                student=user,
                enrollment=enrollment,
                github_link=github_link,
                commit_id="1234567",
            )

    def test_project_list_view_is_paginated(self):
        self.create_paginated_submissions()

        response = self.get_project_list_response()

        self.assertEqual(response.status_code, 200)
        submissions_page = response.context["submissions_page"]
        self.assertEqual(submissions_page.paginator.count, 32)
        submissions_count = len(response.context["submissions"])
        self.assertEqual(submissions_count, 25)
        has_next_page = submissions_page.has_next()
        self.assertTrue(has_next_page)
