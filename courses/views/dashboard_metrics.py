import statistics

from dataclasses import dataclass


@dataclass(frozen=True)
class QuartileValues:
    q25: object
    median: object
    q75: object


def safe_quartiles(data):
    if len(data) < 3:
        return QuartileValues(None, None, None)
    try:
        quartiles = statistics.quantiles(data, n=4)
        return QuartileValues(
            quartiles[0],
            quartiles[1],
            quartiles[2],
        )
    except statistics.StatisticsError:
        return QuartileValues(None, None, None)


def format_median(value):
    if not value:
        return None
    if value % 1 == 0:
        return f"{value:.0f}"
    return f"{value:.1f}"


def submission_values(submissions, field_name):
    values = []
    for submission in submissions:
        value = submission[field_name]
        if value is not None:
            values.append(value)
    return values


def quartile_fields(prefix, values):
    quartiles = safe_quartiles(values)
    formatted_median = format_median(quartiles.median)
    return {
        f"{prefix}_q25": quartiles.q25,
        f"{prefix}_median": quartiles.median,
        f"{prefix}_q75": quartiles.q75,
        f"{prefix}_median_formatted": formatted_median,
    }
