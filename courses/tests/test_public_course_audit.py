from datetime import timedelta
from urllib.parse import urlsplit

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from course_management.datamailer.payloads.registration_confirmations import (
    registration_confirmation_urls,
)
from courses.models import (
    CourseRegistration, Enrollment, Project, ProjectState, Question, Submission,
)
from courses.tests.registration_campaign_base import RegistrationCampaignBase


@override_settings(RELAY_URL="", RELAY_API_KEY="", RELAY_CLIENT="", RELAY_AUDIENCE="")
class PublicCourseAuditTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.requires_registration_approval = True
        self.course.github_repo_url = "https://github.com/DataTalksClub/course-materials"
        self.course.save()
        self.course_url = reverse("course", args=[self.course.slug])

    def test_anonymous_empty_course_is_public_with_apply_and_materials(self):
        response = self.client.get(self.course_url)
        self.assertContains(response, self.course.title)
        self.assertContains(response, "Apply for this course")
        self.assertContains(response, self.course.github_repo_url)
        self.assertFalse(Enrollment.objects.filter(course=self.course).exists())

    def test_pending_empty_course_is_public_with_pending_and_materials(self):
        user = self.create_registered_course_user()
        self.client.force_login(user)
        response = self.client.get(self.course_url)
        self.assertContains(response, "Your application is under review")
        self.assertContains(response, self.course.github_repo_url)
        self.assertNotContains(response, '> Register')
        self.assertFalse(Enrollment.objects.filter(course=self.course).exists())

    def test_legacy_course_route_permanently_redirects_to_public_course(self):
        response = self.client.get(f"/courses/{self.course.slug}/")
        self.assertRedirects(response, self.course_url, status_code=301)

    def test_legacy_unknown_course_is_404(self):
        self.assertEqual(self.client.get('/courses/does-not-exist/').status_code, 404)

    def test_confirmation_email_course_link_resolves(self):
        urls = registration_confirmation_urls(self.campaign, self.course)
        response = self.client.get(urlsplit(urls['course_url']).path)
        self.assertContains(response, self.course.title)

    def create_materials(self):
        homework = self.create_intro_homework()
        homework.homework_url_field = False
        homework.description = "Public homework instructions"
        homework.save()
        Question.objects.create(homework=homework, text="Public audit question", question_type="FF")
        project = Project.objects.create(
            course=self.course, slug="project", title="Public project instructions",
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
        )
        return homework, project

    def test_anonymous_and_pending_can_audit_but_cannot_submit(self):
        homework, project = self.create_materials()
        user = self.create_registered_course_user()
        homework_url = reverse('homework', args=[self.course.slug, homework.slug])
        project_url = reverse('project', args=[self.course.slug, project.slug])
        for pending in (False, True):
            with self.subTest(pending=pending):
                if pending:
                    self.client.force_login(user)
                self.assertContains(self.client.get(self.course_url), 'Intro')
                response = self.client.get(homework_url)
                self.assertContains(response, 'Public homework instructions')
                self.assertContains(response, 'Public audit question')
                self.assertTrue(response.context['disabled'])
                self.assertContains(self.client.get(project_url), 'Public project instructions')
                self.client.post(homework_url, {})
                self.client.post(project_url, {})
                self.client.post(reverse('enrollment', args=[self.course.slug]), {})
                self.assertFalse(Enrollment.objects.filter(course=self.course).exists())
                self.assertFalse(Submission.objects.filter(homework=homework).exists())
                self.assertFalse(project.projectsubmission_set.exists())

    def test_approved_can_submit_homework(self):
        homework, _ = self.create_materials()
        user = self.create_registered_course_user()
        CourseRegistration.objects.filter(user=user).update(status=CourseRegistration.Status.APPROVED)
        self.client.force_login(user)
        url = reverse('homework', args=[self.course.slug, homework.slug])
        response = self.client.post(url, {'time_spent_lectures': '1', 'time_spent_homework': '1'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Submission.objects.filter(homework=homework, student=user).exists())
        self.assertTrue(Enrollment.objects.filter(course=self.course, student=user).exists())
