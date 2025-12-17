from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class WrappedStatistics(models.Model):
    """Pre-calculated statistics for DataTalks.Club Wrapped"""
    
    year = models.IntegerField(unique=True, help_text="The year for which statistics are calculated")
    
    # Control flags
    is_visible = models.BooleanField(
        default=False,
        help_text="Whether to display this wrapped on the main page"
    )
    
    # Platform-wide statistics
    total_participants = models.IntegerField(default=0)
    total_enrollments = models.IntegerField(default=0)
    total_hours = models.FloatField(default=0)
    total_certificates = models.IntegerField(default=0)
    total_points = models.IntegerField(default=0)
    
    # Course popularity data (JSON field)
    course_stats = models.JSONField(
        default=list,
        help_text="List of courses with enrollment counts"
    )
    
    # Leaderboard data (JSON field, top 100)
    leaderboard = models.JSONField(
        default=list,
        help_text="Top 100 users by total score"
    )
    
    # Metadata
    calculated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Wrapped Statistics"
        verbose_name_plural = "Wrapped Statistics"
        ordering = ['-year']
    
    def __str__(self):
        return f"Wrapped {self.year} ({'Visible' if self.is_visible else 'Hidden'})"


class UserWrappedStatistics(models.Model):
    """Pre-calculated statistics for individual user wrapped pages"""
    
    wrapped = models.ForeignKey(
        WrappedStatistics,
        on_delete=models.CASCADE,
        related_name='user_statistics'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='wrapped_statistics'
    )
    
    # User statistics
    total_points = models.IntegerField(default=0)
    total_hours = models.FloatField(default=0)
    homework_count = models.IntegerField(default=0)
    project_count = models.IntegerField(default=0)
    peer_reviews_given = models.IntegerField(default=0)
    learning_in_public_count = models.IntegerField(default=0)
    faq_contributions_count = models.IntegerField(default=0)
    certificates_earned = models.IntegerField(default=0)
    
    # Courses data (JSON field)
    courses = models.JSONField(
        default=list,
        help_text="List of courses with scores"
    )
    
    # Rank
    rank = models.IntegerField(null=True, blank=True)
    
    # Display name
    display_name = models.CharField(max_length=200, blank=True)
    
    # Metadata
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User Wrapped Statistics"
        verbose_name_plural = "User Wrapped Statistics"
        unique_together = [['wrapped', 'user']]
        ordering = ['rank']
    
    def __str__(self):
        return f"{self.display_name} - Wrapped {self.wrapped.year}"
