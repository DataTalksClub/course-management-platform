import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from courses.models import Course, CourseRegistration, User
from courses.constants import CourseState


class CourseLandingPageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="testpass123"
        )
        
        # Create a course in registration state
        self.course_registration = Course.objects.create(
            slug="test-course-registration",
            title="Test Course Registration",
            description="A test course in registration state",
            state=CourseState.REGISTRATION,
            about_content="# Welcome\n\nThis is a **test** course.",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            hero_image_url="https://example.com/hero.jpg",
            meta_description="Test course meta description",
            mailchimp_tag="test-course",
        )
        
        # Create an active course
        self.course_active = Course.objects.create(
            slug="test-course-active",
            title="Test Course Active",
            description="A test course in active state",
            state=CourseState.ACTIVE,
        )
        
        # Create a finished course
        self.course_finished = Course.objects.create(
            slug="test-course-finished",
            title="Test Course Finished",
            description="A test course in finished state",
            state=CourseState.FINISHED,
        )
    
    def test_landing_page_accessible(self):
        """Test that landing page is accessible"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_registration.title)
    
    def test_landing_page_shows_registration_form(self):
        """Test that landing page displays registration form"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        response = self.client.get(url)
        self.assertContains(response, "Register for This Course")
        self.assertContains(response, "name=\"email\"")
        self.assertContains(response, "name=\"name\"")
        self.assertContains(response, "name=\"country\"")
        self.assertContains(response, "name=\"role\"")
    
    def test_landing_page_shows_video_embed(self):
        """Test that landing page embeds YouTube video"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        response = self.client.get(url)
        self.assertContains(response, "youtube.com/embed/dQw4w9WgXcQ")
    
    def test_landing_page_shows_hero_image(self):
        """Test that landing page shows hero image"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        response = self.client.get(url)
        self.assertContains(response, self.course_registration.hero_image_url)
    
    def test_landing_page_renders_markdown(self):
        """Test that landing page renders markdown content"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        response = self.client.get(url)
        self.assertContains(response, "<h1>Welcome</h1>")
        self.assertContains(response, "<strong>test</strong>")
    
    def test_landing_page_seo_meta_tags(self):
        """Test that landing page includes SEO meta tags"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        response = self.client.get(url)
        
        # Check title
        self.assertContains(response, "Test Course Registration - DataTalks.Club")
        
        # Check meta description
        self.assertContains(response, 'name="description"')
        self.assertContains(response, self.course_registration.meta_description)
        
        # Check Open Graph tags
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'property="og:description"')
        self.assertContains(response, 'property="og:image"')
        
        # Check Twitter Card tags
        self.assertContains(response, 'name="twitter:card"')
        self.assertContains(response, 'name="twitter:title"')
    
    def test_registration_form_submission_unauthenticated(self):
        """Test that unauthenticated users can register"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        data = {
            "email": "newuser@example.com",
            "name": "New User",
            "country": "United States",
            "role": "data_scientist",
            "comment": "Looking forward to learning!",
        }
        response = self.client.post(url, data)
        
        # Check registration was created
        self.assertEqual(CourseRegistration.objects.count(), 1)
        registration = CourseRegistration.objects.first()
        self.assertEqual(registration.email, "newuser@example.com")
        self.assertEqual(registration.name, "New User")
        self.assertEqual(registration.country, "United States")
        self.assertEqual(registration.role, "data_scientist")
        self.assertEqual(registration.region, "North America")
    
    def test_registration_form_submission_authenticated(self):
        """Test that authenticated users can register with pre-filled email"""
        self.client.login(email="test@example.com", password="testpass123")
        url = reverse("course_landing", args=[self.course_registration.slug])
        data = {
            "email": "test@example.com",  # Should be pre-filled
            "name": "Test User",
            "country": "Canada",
            "role": "data_engineer",
            "comment": "",
        }
        response = self.client.post(url, data)
        
        # Check registration was created
        self.assertEqual(CourseRegistration.objects.count(), 1)
        registration = CourseRegistration.objects.first()
        self.assertEqual(registration.email, "test@example.com")
        self.assertEqual(registration.course, self.course_registration)
    
    def test_registration_duplicate_prevention(self):
        """Test that duplicate registrations are prevented"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        data = {
            "email": "duplicate@example.com",
            "name": "Duplicate User",
            "country": "United Kingdom",
            "role": "ml_engineer",
            "comment": "",
        }
        
        # First registration
        self.client.post(url, data)
        self.assertEqual(CourseRegistration.objects.count(), 1)
        
        # Second registration with same email
        response = self.client.post(url, data, follow=True)
        self.assertEqual(CourseRegistration.objects.count(), 1)
        # Check that a message was displayed
        messages = list(response.context['messages'])
        self.assertTrue(any('already registered' in str(m).lower() for m in messages))
    
    def test_registration_form_validation(self):
        """Test that form validation works"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        data = {
            "email": "invalid-email",  # Invalid email
            "name": "",  # Required field
            "country": "",  # Required field
            "role": "",  # Required field
            "comment": "",
        }
        response = self.client.post(url, data)
        
        # No registration should be created
        self.assertEqual(CourseRegistration.objects.count(), 0)
        self.assertEqual(response.status_code, 200)
    
    def test_course_registration_state_redirects_to_landing(self):
        """Test that accessing course view in REGISTRATION state redirects to landing page"""
        url = reverse("course", args=[self.course_registration.slug])
        response = self.client.get(url)
        
        # Should redirect to landing page
        self.assertEqual(response.status_code, 302)
        self.assertIn("/about", response.url)
    
    def test_course_registration_state_superuser_can_access(self):
        """Test that superusers can access course view even in REGISTRATION state"""
        # Create superuser
        superuser = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="adminpass123"
        )
        self.client.login(email="admin@example.com", password="adminpass123")
        
        url = reverse("course", args=[self.course_registration.slug])
        response = self.client.get(url)
        
        # Should not redirect - show the course page
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_registration.title)
    
    def test_course_active_state_shows_workspace(self):
        """Test that active courses show the workspace view"""
        url = reverse("course", args=[self.course_active.slug])
        response = self.client.get(url)
        
        # Should show course workspace, not redirect
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_active.title)
    
    def test_course_list_shows_registration_courses(self):
        """Test that course list page shows registration courses separately"""
        url = reverse("course_list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration Open")
        self.assertContains(response, self.course_registration.title)
        self.assertContains(response, self.course_active.title)
        self.assertContains(response, self.course_finished.title)
    
    def test_newsletter_subscription_notice(self):
        """Test that landing page shows newsletter subscription notice"""
        url = reverse("course_landing", args=[self.course_registration.slug])
        response = self.client.get(url)
        self.assertContains(response, "DataTalks.Club newsletter")
    
    def test_youtube_url_parsing_watch_format(self):
        """Test parsing of youtube.com/watch?v= format"""
        course = Course.objects.create(
            slug="test-video-1",
            title="Test Video 1",
            description="Test",
            state=CourseState.REGISTRATION,
            video_url="https://www.youtube.com/watch?v=ABC123&feature=share"
        )
        url = reverse("course_landing", args=[course.slug])
        response = self.client.get(url)
        self.assertContains(response, "youtube.com/embed/ABC123")
    
    def test_youtube_url_parsing_short_format(self):
        """Test parsing of youtu.be/ format"""
        course = Course.objects.create(
            slug="test-video-2",
            title="Test Video 2",
            description="Test",
            state=CourseState.REGISTRATION,
            video_url="https://youtu.be/XYZ789?t=10"
        )
        url = reverse("course_landing", args=[course.slug])
        response = self.client.get(url)
        self.assertContains(response, "youtube.com/embed/XYZ789")
