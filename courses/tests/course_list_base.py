from dataclasses import dataclass

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Project,
    ProjectState,
)


@dataclass(frozen=True)
class HomeworkFixtureData:
    slug: str
    title: str
    description: str
    days_due: int
    state: str


@dataclass(frozen=True)
class ProjectFixtureData:
    title: str
    slug: str
    state: str
    submission_days: int


class CourseListViewTestBase(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course-2",
            description="Test Course Description",
        )
        self.create_homeworks()
        self.create_projects()

    def create_homework(self, data: HomeworkFixtureData):
        return Homework.objects.create(
            slug=data.slug,
            course=self.course,
            title=data.title,
            description=data.description,
            due_date=timezone.now() + timezone.timedelta(days=data.days_due),
            state=data.state,
        )

    def create_homeworks(self):
        scored_homework_data = HomeworkFixtureData(
            slug="scored-homework",
            title="Scored Homework",
            description="This homework is already scored.",
            days_due=-1,
            state=HomeworkState.SCORED.value,
        )
        self.create_homework(scored_homework_data)
        submitted_homework_data = HomeworkFixtureData(
            slug="submitted-homework",
            title="Submitted Homework",
            description="Homework with submitted answers.",
            days_due=7,
            state=HomeworkState.OPEN.value,
        )
        self.create_homework(submitted_homework_data)
        unscored_homework_data = HomeworkFixtureData(
            slug="unscored-homework",
            title="Homework Without Submissions",
            description="Homework without any submissions yet.",
            days_due=14,
            state=HomeworkState.OPEN.value,
        )
        self.create_homework(unscored_homework_data)

    def create_project(self, data: ProjectFixtureData):
        return Project.objects.create(
            course=self.course,
            title=data.title,
            slug=data.slug,
            state=data.state,
            submission_due_date=timezone.now()
            + timezone.timedelta(days=data.submission_days),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

    def create_projects(self):
        open_project_data = ProjectFixtureData(
            title="Open Project",
            slug="open-project",
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
            submission_days=7,
        )
        self.create_project(open_project_data)
        completed_project_data = ProjectFixtureData(
            title="Completed Project",
            slug="completed-project",
            state=ProjectState.COMPLETED.value,
            submission_days=-7,
        )
        self.create_project(completed_project_data)

    def create_archived_course_fixture(self):
        archive_course = Course.objects.create(
            title="Archived Course 2024",
            slug="archived-course-2024",
            description="Past course summary.",
            finished=True,
        )
        homework_due_date = timezone.now()
        Homework.objects.create(
            slug="archived-homework",
            course=archive_course,
            title="Archived Homework",
            due_date=homework_due_date,
            state=HomeworkState.SCORED.value,
        )
        submission_due_date = timezone.now()
        peer_review_due_date = timezone.now()
        Project.objects.create(
            course=archive_course,
            title="Archived Project",
            slug="archived-project",
            state=ProjectState.COMPLETED.value,
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
        )
        return archive_course

    def configure_active_course_metadata(self):
        self.course.start_date = timezone.datetime(2026, 1, 15).date()
        self.course.end_date = timezone.datetime(2026, 4, 15).date()
        self.course.description = "Database-provided course summary."
        self.course.registration_url = (
            "https://courses.datatalks.club/test-course/register"
        )
        self.course.github_repo_url = (
            "https://github.com/DataTalksClub/test-course"
        )
        self.course.save()

    def active_course_from_response(self, response):
        active_courses = response.context["active_courses"]
        for course in active_courses:
            if course.slug == self.course.slug:
                return course
        return None

    def course_card_html(self, content, course):
        course_url = reverse("course", kwargs={"course_slug": course.slug})
        link_position = content.index(f'href="{course_url}"')
        card_start = content.rfind("<article", 0, link_position)
        card_end = content.index("</article>", link_position)
        return content[card_start:card_end]

    def course_archive_row_html(self, content, course):
        archive_url = reverse("course", kwargs={"course_slug": course.slug})
        link_position = content.index(f'href="{archive_url}"')
        row_end = content.index("</a>", link_position)
        return content[link_position:row_end]

    def assert_active_course_metadata(self, response):
        course = self.active_course_from_response(response)
        self.assertEqual(course.home_duration_label, "13 weeks")
        self.assertEqual(
            course.home_current_assignment_label,
            "Next assignment",
        )
        self.assertEqual(
            course.home_current_assignment["title"],
            "Submitted Homework",
        )

    def assert_active_course_card(self, response):
        content = response.content.decode()
        course_card = self.course_card_html(content, self.course)
        self.assertNotIn(">Homework</dt>", course_card)
        self.assertNotIn(">Projects</dt>", course_card)

    def assert_archive_course_row(self, response, archive_course):
        content = response.content.decode()
        archive_row = self.course_archive_row_html(content, archive_course)
        self.assertNotIn("homework</span>", archive_row)
        self.assertNotIn("projects</span>", archive_row)

    def visible_course_slugs(self, response):
        active_courses = response.context["active_courses"]
        finished_courses = response.context["finished_courses"]
        all_courses = list(active_courses) + list(finished_courses)
        course_slugs = []
        for course in all_courses:
            course_slugs.append(course.slug)
        return course_slugs

    def course_list_response(self):
        url = reverse("course_list")
        response = self.client.get(url)
        return response

    def course_card_for(self, response, course):
        content = response.content.decode()
        course_url = reverse("course", kwargs={"course_slug": course.slug})
        course_link_position = content.index(f'href="{course_url}"')
        card_start = content.rfind("<article", 0, course_link_position)
        card_end = content.index("</article>", course_link_position)
        course_card = content[card_start:card_end]
        return course_card
