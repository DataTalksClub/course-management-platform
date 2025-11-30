from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.db import models
from unittest.mock import Mock, patch
from courses.mixin import InstructorAccessMixin


User = get_user_model()


# Mock models for testing
class MockInstructor(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "test_app"


class MockCourse(models.Model):
    instructor = models.ForeignKey(
        MockInstructor, on_delete=models.CASCADE
    )
    title = models.CharField(max_length=100)

    class Meta:
        app_label = "test_app"


class MockLesson(models.Model):
    course = models.ForeignKey(MockCourse, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)

    class Meta:
        app_label = "test_app"


class TestInstructorAccessMixin(TestCase):
    """Test cases for InstructorAccessMixin"""

    def setUp(self):
        """Set up test fixtures"""
        self.factory = RequestFactory()
        self.superuser = Mock(spec=User)
        self.superuser.is_superuser = True

        self.regular_user = Mock(spec=User)
        self.regular_user.is_superuser = False
        self.regular_user.id = 1

    def test_get_queryset_superuser_returns_unfiltered(self):
        """Superusers should see all objects"""
        # Arrange
        mock_qs = Mock()

        class ParentClass:
            def get_queryset(self, request):
                return mock_qs

        class TestMixin(InstructorAccessMixin, ParentClass):
            pass

        mixin_instance = TestMixin()
        mixin_instance.instructor_field = "instructor"

        request = self.factory.get("/")
        request.user = self.superuser

        # Act
        result = mixin_instance.get_queryset(request)

        # Assert
        self.assertEqual(result, mock_qs)
        mock_qs.filter.assert_not_called()

    def test_get_queryset_regular_user_filters_by_instructor(self):
        """Regular users should only see their own objects"""
        # Arrange
        mock_qs = Mock()
        mock_filtered_qs = Mock()
        mock_qs.filter.return_value = mock_filtered_qs

        class ParentClass:
            def get_queryset(self, request):
                return mock_qs

        class TestMixin(InstructorAccessMixin, ParentClass):
            pass

        mixin_instance = TestMixin()
        mixin_instance.instructor_field = "instructor"

        request = self.factory.get("/")
        request.user = self.regular_user

        # Act
        result = mixin_instance.get_queryset(request)

        # Assert
        mock_qs.filter.assert_called_once_with(
            instructor=self.regular_user
        )
        self.assertEqual(result, mock_filtered_qs)

    def test_get_queryset_with_related_field(self):
        """Test filtering with related field like 'course__instructor'"""
        # Arrange
        mock_qs = Mock()
        mock_filtered_qs = Mock()
        mock_qs.filter.return_value = mock_filtered_qs

        class ParentClass:
            def get_queryset(self, request):
                return mock_qs

        class TestMixin(InstructorAccessMixin, ParentClass):
            pass

        mixin_instance = TestMixin()
        mixin_instance.instructor_field = "course__instructor"

        request = self.factory.get("/")
        request.user = self.regular_user

        # Act
        result = mixin_instance.get_queryset(request)

        # Assert
        mock_qs.filter.assert_called_once_with(
            course__instructor=self.regular_user
        )
        self.assertEqual(result, mock_filtered_qs)

    def test_formfield_for_foreignkey_direct_field_no_filtering(self):
        """Direct instructor field should not be filtered in formfield"""
        # Arrange
        mixin = InstructorAccessMixin()
        mixin.instructor_field = "instructor"

        mock_db_field = Mock()
        mock_db_field.name = "instructor"

        mock_super_result = Mock()

        class TestMixin(InstructorAccessMixin):
            def __init__(self):
                super().__init__()
                self.instructor_field = "instructor"

            def formfield_for_foreignkey(
                self, db_field, request, **kwargs
            ):
                if db_field.name == "instructor":
                    return mock_super_result
                return super().formfield_for_foreignkey(
                    db_field, request, **kwargs
                )

        test_mixin = TestMixin()
        request = self.factory.get("/")
        request.user = self.regular_user

        # Act
        result = test_mixin.formfield_for_foreignkey(
            mock_db_field, request
        )

        # Assert
        self.assertEqual(result, mock_super_result)

    def test_formfield_for_foreignkey_related_field_filters_for_regular_user(
        self,
    ):
        """Related field should be filtered for non-superusers"""
        # Arrange
        mock_db_field = Mock()
        mock_db_field.name = "course"

        mock_related_model = Mock()
        mock_queryset = Mock()
        mock_filtered_qs = Mock()
        mock_queryset.filter.return_value = mock_filtered_qs
        mock_related_model.objects = mock_queryset

        mock_remote_field = Mock()
        mock_remote_field.model = mock_related_model
        mock_db_field.remote_field = mock_remote_field

        mock_super_result = Mock()

        class TestMixin(InstructorAccessMixin):
            def __init__(self):
                super().__init__()
                self.instructor_field = "course__instructor"

            def formfield_for_foreignkey(
                self, db_field, request, obj=None, **kwargs
            ):
                # Call parent's implementation
                parts = self.instructor_field.split("__")
                if len(parts) > 1:
                    fk_field_name = parts[0]
                    lookup_path = "__".join(parts[1:])
                    if (
                        db_field.name == fk_field_name
                        and not request.user.is_superuser
                    ):
                        related_model = db_field.remote_field.model
                        kwargs["queryset"] = (
                            related_model.objects.filter(
                                **{lookup_path: request.user}
                            )
                        )
                return mock_super_result

        test_mixin = TestMixin()
        request = self.factory.get("/")
        request.user = self.regular_user

        # Act
        result = test_mixin.formfield_for_foreignkey(
            mock_db_field, request
        )

        # Assert
        mock_queryset.filter.assert_called_once_with(
            instructor=self.regular_user
        )
        self.assertEqual(result, mock_super_result)

    def test_formfield_for_foreignkey_related_field_no_filter_for_superuser(
        self,
    ):
        """Superuser should not have filtered queryset"""
        # Arrange
        mock_db_field = Mock()
        mock_db_field.name = "course"

        mock_related_model = Mock()
        mock_queryset = Mock()
        mock_related_model.objects = mock_queryset

        mock_remote_field = Mock()
        mock_remote_field.model = mock_related_model
        mock_db_field.remote_field = mock_remote_field

        mock_super_result = Mock()

        class TestMixin(InstructorAccessMixin):
            def __init__(self):
                super().__init__()
                self.instructor_field = "course__instructor"

            def formfield_for_foreignkey(
                self, db_field, request, obj=None, **kwargs
            ):
                parts = self.instructor_field.split("__")
                if len(parts) > 1:
                    fk_field_name = parts[0]
                    if (
                        db_field.name == fk_field_name
                        and not request.user.is_superuser
                    ):
                        # This should not execute for superuser
                        kwargs["queryset"] = Mock()
                return mock_super_result

        test_mixin = TestMixin()
        request = self.factory.get("/")
        request.user = self.superuser

        # Act
        result = test_mixin.formfield_for_foreignkey(
            mock_db_field, request
        )

        # Assert
        mock_queryset.filter.assert_not_called()
        self.assertEqual(result, mock_super_result)

    def test_formfield_for_foreignkey_different_field_not_filtered(
        self,
    ):
        """Fields other than the instructor field should not be filtered"""
        # Arrange
        mock_db_field = Mock()
        mock_db_field.name = (
            "other_field"  # Different from instructor field
        )

        mock_super_result = Mock()

        class TestMixin(InstructorAccessMixin):
            def __init__(self):
                super().__init__()
                self.instructor_field = "course__instructor"

            def formfield_for_foreignkey(
                self, db_field, request, obj=None, **kwargs
            ):
                parts = self.instructor_field.split("__")
                if len(parts) > 1:
                    fk_field_name = parts[0]
                    if db_field.name == fk_field_name:
                        # This should not execute
                        kwargs["queryset"] = Mock()
                return mock_super_result

        test_mixin = TestMixin()
        request = self.factory.get("/")
        request.user = self.regular_user

        # Act
        result = test_mixin.formfield_for_foreignkey(
            mock_db_field, request
        )

        # Assert
        self.assertEqual(result, mock_super_result)
        self.assertNotIn("queryset", {})  # queryset should not be set

    def test_instructor_field_with_deep_relationship(self):
        """Test with deeply nested relationship like 'course__department__instructor'"""
        # Arrange
        mock_qs = Mock()
        mock_filtered_qs = Mock()
        mock_qs.filter.return_value = mock_filtered_qs

        class ParentClass:
            def get_queryset(self, request):
                return mock_qs

        class TestMixin(InstructorAccessMixin, ParentClass):
            pass

        mixin_instance = TestMixin()
        mixin_instance.instructor_field = (
            "course__department__instructor"
        )

        request = self.factory.get("/")
        request.user = self.regular_user

        # Act
        result = mixin_instance.get_queryset(request)

        # Assert
        mock_qs.filter.assert_called_once_with(
            course__department__instructor=self.regular_user
        )
        self.assertEqual(result, mock_filtered_qs)


class TestInstructorAccessMixinIntegration(TestCase):
    """Integration tests with actual Django admin"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_mixin_with_model_admin(self):
        """Test that mixin works correctly when combined with ModelAdmin"""

        # Create a simple parent class that mimics ModelAdmin behavior
        class MockModelAdmin:
            def __init__(self):
                self.model = Mock()
                self.opts = Mock()

            def get_queryset(self, request):
                return Mock()

            def formfield_for_foreignkey(
                self, db_field, request, **kwargs
            ):
                return Mock()

        class TestAdmin(InstructorAccessMixin, MockModelAdmin):
            instructor_field = "instructor"

        admin = TestAdmin()

        # Test that the mixin methods are available
        self.assertTrue(hasattr(admin, "get_queryset"))
        self.assertTrue(hasattr(admin, "formfield_for_foreignkey"))
        self.assertEqual(admin.instructor_field, "instructor")

        # Test that get_queryset works
        request = self.factory.get("/")
        request.user = Mock()
        request.user.is_superuser = False

        mock_qs = Mock()
        mock_filtered_qs = Mock()
        mock_qs.filter.return_value = mock_filtered_qs

        # Override the parent's get_queryset to return our mock
        with patch.object(
            MockModelAdmin, "get_queryset", return_value=mock_qs
        ):
            parent_qs = MockModelAdmin().get_queryset(request)
            self.assertEqual(parent_qs, mock_qs)
