"""Shared helpers for rendering HomeworkStatistics / ProjectStatistics.

Both statistics models expose the same per-field distribution
(min/max/avg/q1/median/q3) and render it as a list of
``(section_label, [rows], section_icon)`` tuples for templates. This module
keeps that display structure in one place.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StatRow:
    stats_type: str
    label: str
    icon: str


@dataclass(frozen=True)
class StatSection:
    field_name: str
    label: str
    icon: str


STAT_ROWS = [
    StatRow("min", "Minimum", "fas fa-arrow-down"),
    StatRow("max", "Maximum", "fas fa-arrow-up"),
    StatRow("avg", "Average", "fas fa-equals"),
    StatRow("q1", "25th Percentile", "fas fa-percentage"),
    StatRow("median", "Median", "fas fa-percentage"),
    StatRow("q3", "75th Percentile", "fas fa-percentage"),
]


def homework_stat_sections():
    sections = []
    questions_score = StatSection(
        "questions_score",
        "Questions score",
        "fas fa-question-circle",
    )
    sections.append(questions_score)
    total_score = StatSection("total_score", "Total score", "fas fa-star")
    sections.append(total_score)
    lecture_time = StatSection(
        "time_spent_lectures",
        "Time spent on lectures",
        "fas fa-book-reader",
    )
    sections.append(lecture_time)
    homework_time = StatSection(
        "time_spent_homework",
        "Time spent on homework",
        "fas fa-clock",
    )
    sections.append(homework_time)
    learning_in_public = StatSection(
        "learning_in_public_score",
        "Learning in public score",
        "fas fa-globe",
    )
    sections.append(learning_in_public)
    return sections


def project_score_stat_sections():
    sections = []
    project_score = StatSection(
        "project_score",
        "Project score",
        "fas fa-project-diagram",
    )
    sections.append(project_score)
    project_learning_in_public = StatSection(
        "project_learning_in_public_score",
        "Project learning in public score",
        "fas fa-globe",
    )
    sections.append(project_learning_in_public)
    return sections


def project_peer_review_stat_sections():
    sections = []
    peer_review_score = StatSection(
        "peer_review_score",
        "Peer review score",
        "fas fa-users",
    )
    sections.append(peer_review_score)
    peer_review_learning_in_public = StatSection(
        "peer_review_learning_in_public_score",
        "Peer review learning in public score",
        "fas fa-share-alt",
    )
    sections.append(peer_review_learning_in_public)
    return sections


def project_summary_stat_sections():
    sections = []
    total_score = StatSection("total_score", "Total score", "fas fa-star")
    sections.append(total_score)
    time_spent = StatSection(
        "time_spent",
        "Time spent on project",
        "fas fa-clock",
    )
    sections.append(time_spent)
    return sections


def project_stat_sections():
    sections = []
    score_sections = project_score_stat_sections()
    sections.extend(score_sections)
    peer_review_sections = project_peer_review_stat_sections()
    sections.extend(peer_review_sections)
    summary_sections = project_summary_stat_sections()
    sections.extend(summary_sections)
    return sections


def build_stat_fields(stats, sections):
    """Build the display structure for a statistics model.

    ``sections`` is a list of ``StatSection`` objects.
    Returns a list of ``(section_label, rows, section_icon)`` where each row is
    ``(value, row_label, row_icon)``.
    """
    results = []
    for section in sections:
        rows = []
        for stat_row in STAT_ROWS:
            value = stats.get_value(
                section.field_name,
                stat_row.stats_type,
            )
            row = (value, stat_row.label, stat_row.icon)
            rows.append(row)
        section_record = (section.label, rows, section.icon)
        results.append(section_record)
    return results
