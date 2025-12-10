import logging
from typing import Dict, Any
from datetime import datetime

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.contrib.auth.decorators import login_required

from courses.models import (
    Course,
    Enrollment,
    Submission,
    ProjectSubmission,
)

logger = logging.getLogger(__name__)


def get_2025_date_range():
    """Get the start and end date for 2025"""
    year_2025_start = timezone.make_aware(datetime(2025, 1, 1))
    year_2025_end = timezone.make_aware(datetime(2025, 12, 31, 23, 59, 59))
    return year_2025_start, year_2025_end


def get_platform_statistics_2025() -> Dict[str, Any]:
    """Calculate platform-wide statistics for 2025"""
    year_start, year_end = get_2025_date_range()
    
    # Get enrollments in 2025
    enrollments_2025 = Enrollment.objects.filter(
        enrollment_date__gte=year_start,
        enrollment_date__lte=year_end
    )
    
    total_participants = enrollments_2025.values('student').distinct().count()
    
    # Get course popularity - enrollments per course in 2025
    course_stats = enrollments_2025.values(
        'course__title', 'course__slug'
    ).annotate(
        enrollment_count=Count('id')
    ).order_by('-enrollment_count')
    
    # Calculate total hours spent in 2025
    # Homework hours
    homework_submissions_2025 = Submission.objects.filter(
        submitted_at__gte=year_start,
        submitted_at__lte=year_end
    ).aggregate(
        total_lecture_hours=Sum('time_spent_lectures'),
        total_homework_hours=Sum('time_spent_homework')
    )
    
    # Project hours
    project_submissions_2025 = ProjectSubmission.objects.filter(
        submitted_at__gte=year_start,
        submitted_at__lte=year_end
    ).aggregate(
        total_project_hours=Sum('time_spent')
    )
    
    total_hours = 0
    if homework_submissions_2025['total_lecture_hours']:
        total_hours += homework_submissions_2025['total_lecture_hours']
    if homework_submissions_2025['total_homework_hours']:
        total_hours += homework_submissions_2025['total_homework_hours']
    if project_submissions_2025['total_project_hours']:
        total_hours += project_submissions_2025['total_project_hours']
    
    # Count certificates (enrollments with certificate_url in 2025)
    total_certificates = enrollments_2025.exclude(
        Q(certificate_url__isnull=True) | Q(certificate_url='')
    ).count()
    
    # Total points earned in 2025
    total_points = enrollments_2025.aggregate(
        total_score=Sum('total_score')
    )['total_score'] or 0
    
    return {
        'total_participants': total_participants,
        'total_enrollments': enrollments_2025.count(),
        'course_stats': list(course_stats),
        'total_hours': round(total_hours, 1) if total_hours else 0,
        'total_certificates': total_certificates,
        'total_points': total_points,
    }


def get_user_statistics_2025(user) -> Dict[str, Any]:
    """Calculate user-specific statistics for 2025"""
    year_start, year_end = get_2025_date_range()
    
    # Get user's enrollments in 2025
    user_enrollments = Enrollment.objects.filter(
        student=user,
        enrollment_date__gte=year_start,
        enrollment_date__lte=year_end
    ).select_related('course')
    
    # Total points
    total_points = user_enrollments.aggregate(
        total_score=Sum('total_score')
    )['total_score'] or 0
    
    # Courses enrolled
    courses_enrolled = [
        {
            'title': e.course.title,
            'score': e.total_score
        }
        for e in user_enrollments
    ]
    
    # Calculate hours spent
    homework_submissions = Submission.objects.filter(
        student=user,
        submitted_at__gte=year_start,
        submitted_at__lte=year_end
    ).aggregate(
        total_lecture_hours=Sum('time_spent_lectures'),
        total_homework_hours=Sum('time_spent_homework')
    )
    
    project_submissions = ProjectSubmission.objects.filter(
        student=user,
        submitted_at__gte=year_start,
        submitted_at__lte=year_end
    ).aggregate(
        total_project_hours=Sum('time_spent')
    )
    
    total_hours = 0
    if homework_submissions['total_lecture_hours']:
        total_hours += homework_submissions['total_lecture_hours']
    if homework_submissions['total_homework_hours']:
        total_hours += homework_submissions['total_homework_hours']
    if project_submissions['total_project_hours']:
        total_hours += project_submissions['total_project_hours']
    
    # Count certificates
    certificates_earned = user_enrollments.exclude(
        Q(certificate_url__isnull=True) | Q(certificate_url='')
    ).count()
    
    return {
        'total_points': total_points,
        'courses_enrolled': courses_enrolled,
        'total_hours': round(total_hours, 1) if total_hours else 0,
        'certificates_earned': certificates_earned,
    }


def get_2025_leaderboard(limit=1200):
    """Get top participants for 2025 (limited to 1200)"""
    year_start, year_end = get_2025_date_range()
    
    # Get all enrollments from 2025, ordered by total score
    # We'll aggregate by student and sum their scores across all courses
    leaderboard = Enrollment.objects.filter(
        enrollment_date__gte=year_start,
        enrollment_date__lte=year_end,
        display_on_leaderboard=True
    ).values(
        'student_id',
        'display_name',
        'student__email'
    ).annotate(
        total_score=Sum('total_score')
    ).order_by('-total_score')[:limit]
    
    # Add rank
    ranked_leaderboard = []
    for idx, entry in enumerate(leaderboard, start=1):
        ranked_leaderboard.append({
            'rank': idx,
            'display_name': entry['display_name'],
            'total_score': entry['total_score'],
            'student_id': entry['student_id']
        })
    
    return ranked_leaderboard


def wrapped_view(request: HttpRequest) -> HttpResponse:
    """Main view for DataTalks.Club Wrapped 2025"""
    
    # Get platform statistics
    platform_stats = get_platform_statistics_2025()
    
    # Get user statistics if authenticated
    user_stats = None
    user_rank = None
    if request.user.is_authenticated:
        user_stats = get_user_statistics_2025(request.user)
        
        # Find user's rank in the leaderboard
        year_start, year_end = get_2025_date_range()
        user_enrollments = Enrollment.objects.filter(
            student=request.user,
            enrollment_date__gte=year_start,
            enrollment_date__lte=year_end
        )
        
        if user_enrollments.exists():
            user_total = user_enrollments.aggregate(
                total=Sum('total_score')
            )['total'] or 0
            
            # Count how many students have a higher total
            higher_count = Enrollment.objects.filter(
                enrollment_date__gte=year_start,
                enrollment_date__lte=year_end,
                display_on_leaderboard=True
            ).values('student_id').annotate(
                total=Sum('total_score')
            ).filter(total__gt=user_total).count()
            
            user_rank = higher_count + 1
    
    # Get leaderboard (top 1200)
    leaderboard = get_2025_leaderboard(limit=1200)
    
    context = {
        'year': 2025,
        'platform_stats': platform_stats,
        'user_stats': user_stats,
        'user_rank': user_rank,
        'leaderboard': leaderboard,
    }
    
    return render(request, 'courses/wrapped.html', context)
