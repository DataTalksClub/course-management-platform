from api.tests.project_api_base import ProjectAPITestBase


class ProjectsAPITestCase(ProjectAPITestBase):
    def test_list_projects(self):
        self._create_project()
        url = f"/api/courses/{self.course.slug}/projects/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(data["projects"][0]["submissions_count"], 0)
        self.assertTrue(data["projects"][0]["can_delete"])

    def test_get_project_detail(self):
        project = self._create_project()
        url = f"/api/courses/{self.course.slug}/projects/{project.id}/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], project.id)
        self.assertEqual(data["slug"], "proj1")
        self.assertTrue(data["can_delete"])
