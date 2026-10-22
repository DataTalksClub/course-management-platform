from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from courses.models import (
    CourseRegistration,
    Enrollment,
    Project,
    ProjectState,
    ProjectSubmission,
    Submission,
)
from courses.tests.registration_campaign_base import RegistrationCampaignBase


@override_settings(
    RELAY_URL="",
    RELAY_API_KEY="",
    RELAY_CLIENT="",
    RELAY_AUDIENCE="",
)
class RegistrationWallTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.requires_registration_approval = True
        self.course.save(update_fields=["requires_registration_approval"])
        self.homework = self.create_intro_homework()
        self.project = self.create_open_project()
        self.user = CustomUser.objects.create_user(
            username="wall-student",
            email="wall-student@example.com",
            password="test",
        )

    def create_open_project(self):
        now = timezone.now()
        return Project.objects.create(
            course=self.course,
            slug="open-project",
            title="Open Project",
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
            submission_due_date=now + timedelta(days=7),
            peer_review_due_date=now + timedelta(days=14),
        )

    def homework_url(self):
        return reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def project_url(self):
        return reverse(
            "project",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

    def enrollment_url(self):
        return reverse(
            "enrollment",
            kwargs={"course_slug": self.course.slug},
        )

    def create_pending_registration(self, user=None):
        email = self.user.email if user is None else user.email
        return CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            user=user,
            email=email,
            name="Wall Student",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.ML_ENGINEER,
            experience="3 years ML",
            accepted_newsletter=True,
        )

    def test_new_registration_defaults_to_pending(self):
        registration = self.create_pending_registration()
        self.assertEqual(
            registration.status, CourseRegistration.Status.PENDING
        )

    def test_wall_on_homework_get_blocked_without_enrollment(self):
        self.client.force_login(self.user)
        response = self.client.get(self.homework_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration approval required")
        self.assertFalse(
            Enrollment.objects.filter(
                student=self.user, course=self.course
            ).exists()
        )

    def test_wall_on_homework_post_blocked(self):
        self.client.force_login(self.user)
        response = self.client.post(self.homework_url(), {})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Enrollment.objects.filter(
                student=self.user, course=self.course
            ).exists()
        )
        self.assertFalse(
            Submission.objects.filter(
                homework=self.homework, student=self.user
            ).exists()
        )

    def test_wall_on_project_get_blocked_without_enrollment(self):
        self.client.force_login(self.user)
        response = self.client.get(self.project_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration approval required")
        self.assertFalse(
            Enrollment.objects.filter(
                student=self.user, course=self.course
            ).exists()
        )

    def test_wall_on_project_post_blocked(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.project_url(),
            {"github_link": "https://github.com/example/repo"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ProjectSubmission.objects.filter(
                project=self.project, student=self.user
            ).exists()
        )

    def test_wall_on_enrollment_view_redirects_without_enrolling(self):
        self.client.force_login(self.user)
        response = self.client.get(self.enrollment_url())

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Enrollment.objects.filter(
                student=self.user, course=self.course
            ).exists()
        )

    def test_wall_on_anonymous_homework_shows_apply_notice(self):
        response = self.client.get(self.homework_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration approval required")

    def test_wall_on_course_page_shows_apply_banner(self):
        self.client.force_login(self.user)
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Application required")
        self.assertContains(response, "Apply for this course")

    def test_wall_on_course_page_shows_pending_state(self):
        self.create_pending_registration(user=self.user)
        self.client.force_login(self.user)
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "under review")

    def test_rejected_registration_stays_blocked(self):
        registration = self.create_pending_registration(user=self.user)
        registration.status = CourseRegistration.Status.REJECTED
        registration.save(update_fields=["status"])
        self.client.force_login(self.user)

        response = self.client.get(self.homework_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration approval required")
        self.assertFalse(
            Enrollment.objects.filter(
                student=self.user, course=self.course
            ).exists()
        )

    def test_approved_registration_unlocks_homework(self):
        registration = self.create_pending_registration(user=self.user)
        registration.status = CourseRegistration.Status.APPROVED
        registration.save(update_fields=["status"])
        self.client.force_login(self.user)

        response = self.client.get(self.homework_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, "Registration approval required"
        )
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.user, course=self.course
            ).exists()
        )

    def test_registration_page_shows_wall_disclaimer(self):
        response = self.client.get(self.campaign_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Application only")
        self.assertContains(response, "limited seats")

    def test_wall_form_requires_experience(self):
        payload = self.registration_payload()
        payload.pop("experience", None)
        response = self.client.post(self.campaign_url(), payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 0)

    def test_wall_form_accepts_full_application_as_pending(self):
        payload = self.registration_payload()
        payload["experience"] = "3 years building ML systems"
        payload["why_join"] = "I want to go to production"
        payload["linkedin_url"] = "https://www.linkedin.com/in/example"
        payload["github_url"] = "https://github.com/example"
        payload["prereq_python"] = "on"
        payload["prereq_docker"] = "on"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.campaign_url(), payload)

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(
            registration.status, CourseRegistration.Status.PENDING
        )
        self.assertEqual(
            registration.experience, "3 years building ML systems"
        )
        self.assertEqual(registration.why_join, "I want to go to production")
        self.assertTrue(registration.prereq_python)
        self.assertTrue(registration.prereq_docker)
        self.assertFalse(
            Enrollment.objects.filter(course=self.course).exists()
        )


@override_settings(
    RELAY_URL="",
    RELAY_API_KEY="",
    RELAY_CLIENT="",
    RELAY_AUDIENCE="",
)
class RegistrationWallOffTests(RegistrationCampaignBase):
    def test_wall_off_homework_get_creates_enrollment(self):
        homework = self.create_intro_homework()
        user = CustomUser.objects.create_user(
            username="open-student",
            email="open-student@example.com",
            password="test",
        )
        self.client.force_login(user)
        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": homework.slug,
            },
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, "Registration approval required"
        )
        self.assertTrue(
            Enrollment.objects.filter(
                student=user, course=self.course
            ).exists()
        )


@override_settings(
    RELAY_URL="",
    RELAY_API_KEY="",
    RELAY_CLIENT="",
    RELAY_AUDIENCE="",
)
class RegistrationReviewTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.requires_registration_approval = True
        self.course.save(update_fields=["requires_registration_approval"])
        self.staff = CustomUser.objects.create_user(
            username="reviewer",
            email="reviewer@example.com",
            password="test",
            is_staff=True,
        )
        self.student = CustomUser.objects.create_user(
            username="applicant",
            email="applicant@example.com",
            password="test",
        )

    def create_pending_registration(self):
        return CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email=self.student.email,
            name="Applicant",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.ML_ENGINEER,
            experience="3 years ML",
            accepted_newsletter=True,
        )

    def decide_url(self):
        return reverse(
            "cadmin_campaign_registration_decide",
            kwargs={"campaign_slug": self.campaign.slug},
        )

    def export_url(self):
        return reverse(
            "cadmin_campaign_registrations_export",
            kwargs={"campaign_slug": self.campaign.slug},
        )

    def test_non_staff_cannot_decide(self):
        registration = self.create_pending_registration()
        self.client.force_login(self.student)

        response = self.client.post(
            self.decide_url(),
            {"registration_id": registration.id, "action": "approve"},
        )

        self.assertEqual(response.status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(
            registration.status, CourseRegistration.Status.PENDING
        )

    def test_approve_links_user_by_email_and_enrolls(self):
        registration = self.create_pending_registration()
        self.assertIsNone(registration.user)
        self.client.force_login(self.staff)

        response = self.client.post(
            self.decide_url(),
            {"registration_id": registration.id, "action": "approve"},
        )

        self.assertEqual(response.status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(
            registration.status, CourseRegistration.Status.APPROVED
        )
        self.assertEqual(registration.user, self.student)
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.student, course=self.course
            ).exists()
        )

    def test_reject_keeps_user_out(self):
        registration = self.create_pending_registration()
        self.client.force_login(self.staff)

        response = self.client.post(
            self.decide_url(),
            {"registration_id": registration.id, "action": "reject"},
        )

        self.assertEqual(response.status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(
            registration.status, CourseRegistration.Status.REJECTED
        )
        self.assertFalse(
            Enrollment.objects.filter(
                student=self.student, course=self.course
            ).exists()
        )

    def test_review_list_shows_status_filter_and_export(self):
        self.create_pending_registration()
        self.client.force_login(self.staff)
        list_url = reverse(
            "cadmin_campaign_registrations",
            kwargs={"campaign_slug": self.campaign.slug},
        )

        response = self.client.get(list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending review")
        self.assertContains(response, "Export CSV")

        filtered = self.client.get(list_url + "?status=approved")
        self.assertEqual(filtered.status_code, 200)
        self.assertContains(filtered, "No registrations found.")

    def test_export_csv_contains_application_fields(self):
        self.create_pending_registration()
        self.client.force_login(self.staff)

        response = self.client.get(self.export_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode()
        header = content.splitlines()[0]
        for column in ("email", "experience", "why_join", "status"):
            self.assertIn(column, header)
        self.assertIn("applicant@example.com", content)
        self.assertIn("3 years ML", content)


@override_settings(
    RELAY_URL="",
    RELAY_API_KEY="",
    RELAY_CLIENT="",
    RELAY_AUDIENCE="",
)
class RegistrationThreeFieldsTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.requires_registration_approval = True
        self.course.save(update_fields=["requires_registration_approval"])

    def test_role_choices_include_founder_and_mlops(self):
        values = dict(CourseRegistration.Role.choices)
        self.assertEqual(values["founder_cto"], "Founder/CTO")
        self.assertEqual(
            values["mlops_platform"], "MLOps/Platform Engineer"
        )

    def test_wall_form_renders_new_fields(self):
        response = self.client.get(self.campaign_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Founder/CTO")
        self.assertContains(response, "MLOps/Platform Engineer")
        self.assertContains(response, "Share my application with Nebius")
        self.assertContains(
            response, "Years of professional software or ML experience"
        )

    def test_wall_form_requires_nebius_consent(self):
        payload = self.registration_payload()
        payload["experience"] = "3 years building ML systems"
        payload.pop("accepted_nebius_sharing", None)
        response = self.client.post(self.campaign_url(), payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 0)

    def test_wall_form_accepts_new_roles_years_and_consent(self):
        payload = self.registration_payload()
        payload["role"] = CourseRegistration.Role.MLOPS_PLATFORM
        payload["experience"] = "3 years building ML systems"
        payload["years_experience"] = (
            CourseRegistration.YearsExperience.THREE_TO_SIX
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.campaign_url(), payload)

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(
            registration.role, CourseRegistration.Role.MLOPS_PLATFORM
        )
        self.assertEqual(registration.years_experience, "3_6")
        self.assertTrue(registration.accepted_nebius_sharing)
        self.assertEqual(
            registration.status, CourseRegistration.Status.PENDING
        )

    def test_years_experience_stays_optional(self):
        payload = self.registration_payload()
        payload["experience"] = "3 years building ML systems"
        payload.pop("years_experience", None)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.campaign_url(), payload)

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(registration.years_experience, "")

    def test_non_wall_form_omits_nebius_consent(self):
        self.course.requires_registration_approval = False
        self.course.save(update_fields=["requires_registration_approval"])

        response = self.client.get(self.campaign_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Share my application with Nebius")

        payload = self.registration_payload()
        payload.pop("accepted_nebius_sharing", None)
        with self.captureOnCommitCallbacks(execute=True):
            post_response = self.client.post(self.campaign_url(), payload)

        self.assertEqual(post_response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertFalse(registration.accepted_nebius_sharing)

    def test_export_csv_contains_new_columns(self):
        staff = CustomUser.objects.create_user(
            username="exporter",
            email="exporter@example.com",
            password="test",
            is_staff=True,
        )
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="three-fields@example.com",
            name="Three Fields",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.FOUNDER_CTO,
            accepted_newsletter=True,
            accepted_nebius_sharing=True,
            years_experience=(
                CourseRegistration.YearsExperience.ONE_TO_THREE
            ),
        )
        self.client.force_login(staff)
        url = reverse(
            "cadmin_campaign_registrations_export",
            kwargs={"campaign_slug": self.campaign.slug},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        header = content.splitlines()[0]
        self.assertIn("years_experience", header)
        self.assertIn("accepted_nebius_sharing", header)
        self.assertIn("founder_cto", content)
