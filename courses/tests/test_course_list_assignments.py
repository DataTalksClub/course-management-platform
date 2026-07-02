from django.utils.html import strip_tags

from courses.models import Course
from courses.tests.course_list_base import CourseListViewTestBase


class CourseListAssignmentPanelTest(CourseListViewTestBase):
    def test_course_list_hides_assignment_panel_without_assignments(self):
        empty_course = Course.objects.create(
            title="No Assignment Course",
            slug="no-assignment-course",
            description="Course without assignments.",
        )

        response = self.course_list_response()

        self.assertEqual(response.status_code, 200)
        course_card = self.course_card_for(response, empty_course)
        self.assertNotIn("Current assignment", course_card)
        self.assertNotIn(">TBA</p>", course_card)
        course_card_words = strip_tags(course_card).split()
        course_card_text = " ".join(course_card_words)
        self.assertNotIn("Dates to be announced", course_card_text)
        self.assertNotIn("TBA", course_card_text)
