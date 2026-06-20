"""Shared helpers for rendering HomeworkStatistics / ProjectStatistics.

Both statistics models expose the same per-field distribution
(min/max/avg/q1/median/q3) and render it as a list of
``(section_label, [rows], section_icon)`` tuples for templates. This module
keeps that display structure in one place.
"""

# (stats_type, row_label, row_icon) for each row within a stat section, in
# display order. stats_type maps to the model attribute via get_value().
STAT_ROWS = [
    ("min", "Minimum", "fas fa-arrow-down"),
    ("max", "Maximum", "fas fa-arrow-up"),
    ("avg", "Average", "fas fa-equals"),
    ("q1", "25th Percentile", "fas fa-percentage"),
    ("median", "Median", "fas fa-percentage"),
    ("q3", "75th Percentile", "fas fa-percentage"),
]


def build_stat_fields(stats, sections):
    """Build the display structure for a statistics model.

    ``sections`` is a list of ``(field_name, section_label, section_icon)``.
    Returns a list of ``(section_label, rows, section_icon)`` where each row is
    ``(value, row_label, row_icon)``.
    """
    results = []
    for field_name, section_label, section_icon in sections:
        rows = [
            (stats.get_value(field_name, stats_type), row_label, row_icon)
            for stats_type, row_label, row_icon in STAT_ROWS
        ]
        results.append((section_label, rows, section_icon))
    return results
