from dataclasses import dataclass
from datetime import datetime

from courses.models import WrappedStatistics


@dataclass(frozen=True)
class UserWrappedStatData:
    stats: WrappedStatistics
    student: object
    homework_submissions: list
    project_submissions: list
    enrollments: list
    peer_reviews_count: int
    leaderboard_data: list


@dataclass(frozen=True)
class UserWrappedMetrics:
    total_points: int
    total_hours: float
    learning_in_public_count: int
    faq_contributions_count: int
    certificates_earned: int
    courses: list
    rank: int | None
    display_name: str


@dataclass
class WrappedLeaderboardUserScore:
    student: object
    display_name: str
    total_score: int = 0


@dataclass(frozen=True)
class WrappedActiveEnrollmentData:
    students_with_activity: set
    enrollments: object
    courses: set


@dataclass(frozen=True)
class WrappedActivityByStudent:
    homework_by_student: dict
    project_by_student: dict
    enrollment_by_student: dict


@dataclass(frozen=True)
class WrappedActivity:
    year_start: datetime
    year_end: datetime
    homework_submissions: object
    project_submissions: object
    students_with_activity: set
    enrollments: object
    courses: set


@dataclass(frozen=True)
class UserWrappedStatsBuildData:
    stats: WrappedStatistics
    students_with_activity: set
    homework_by_student: dict
    project_by_student: dict
    enrollment_by_student: dict
    peer_review_counts: dict
    leaderboard_data: list
