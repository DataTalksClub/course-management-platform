from api.tests.course_api_base import CourseAPITestBase


class CourseAuthAPITestCase(CourseAPITestBase):
    def test_course_mutations_require_staff_token(self):
        client = self.non_staff_client()

        responses = self.non_staff_course_mutation_responses(client)

        for response in responses:
            self.assert_staff_token_required(response)
        self.assert_course_unchanged_after_forbidden_mutations()
