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
        results.append((section.label, rows, section.icon))
    return results
