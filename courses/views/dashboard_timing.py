# Buckets of how early a submission arrived, keyed by a lower bound in days
# before the due date. Ordered from earliest to latest.
TIMING_BUCKETS = (
    (7.0, "A week or more early"),
    (3.0, "3-7 days early"),
    (1.0, "1-3 days early"),
    (0.0, "Final day"),
    (float("-inf"), "After the deadline"),
)


def dashboard_submission_timing(
    homework_submissions, due_dates_by_homework_id=None
):
    """Buckets how early submissions arrived relative to their due date.

    Consumes the same rows dashboard_homework_submissions() already
    fetched: issuing a separate query here meant a second full scan of
    every submission in the course on each dashboard cold build.
    """
    counts = {label: 0 for _, label in TIMING_BUCKETS}
    total = 0
    for submission in homework_submissions:
        if isinstance(submission, tuple):
            hw_id = submission[0]
            submitted_at = submission[5]
            due_date = (
                due_dates_by_homework_id.get(hw_id)
                if due_dates_by_homework_id
                else None
            )
        else:
            submitted_at = submission.get("submitted_at")
            due_date = submission.get("homework__due_date")
            if due_date is None and due_dates_by_homework_id:
                due_date = due_dates_by_homework_id.get(
                    submission.get("homework_id")
                )
        if submitted_at is None or due_date is None:
            continue
        days_before = (due_date - submitted_at).days
        if days_before >= 7:
            counts["A week or more early"] += 1
        elif days_before >= 3:
            counts["3-7 days early"] += 1
        elif days_before >= 1:
            counts["1-3 days early"] += 1
        elif days_before >= 0:
            counts["Final day"] += 1
        else:
            counts["After the deadline"] += 1
        total += 1

    if total == 0:
        return []

    return [
        {
            "label": label,
            "count": counts[label],
            "pct": round(counts[label] / total * 100, 1),
        }
        for _, label in TIMING_BUCKETS
    ]


def timing_bucket_label(days_before):
    for lower_bound, label in TIMING_BUCKETS:
        if days_before >= lower_bound:
            return label
    return TIMING_BUCKETS[-1][1]
