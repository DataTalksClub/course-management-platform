from courses.tests.course_list_base import CourseListViewTestBase


class CourseListMetadataTest(CourseListViewTestBase):
    def test_course_list_shows_active_course_metadata(self):
        archive_course = self.create_archived_course_fixture()
        self.configure_active_course_metadata()

        response = self.course_list_response()

        self.assertEqual(response.status_code, 200)
        self.assert_active_course_metadata(response)
        self.assertContains(response, "Jan 15, 2026")
        self.assertContains(response, "Apr 15, 2026")
        self.assertContains(response, "13 weeks")
        self.assertContains(response, "Database-provided course summary.")
        self.assertContains(response, "Submitted Homework")
        self.assert_active_course_card(response)
        self.assert_archive_course_row(response, archive_course)
        self.assertNotContains(
            response,
            "https://courses.datatalks.club/test-course/register",
        )
        self.assertContains(
            response,
            "https://github.com/DataTalksClub/test-course",
        )
        self.assertNotContains(response, "home-stats-grid")
        self.assertNotContains(response, "Course page")
