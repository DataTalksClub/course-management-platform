from .serializer_counts import annotated_or_count


def review_criteria_to_dict(criteria):
    scores_count = annotated_or_count(
        criteria, "scores_count", "projectevaluationscore_set"
    )
    delete_blockers = []
    if scores_count:
        delete_blockers.append("has_scores")
    return {
        "id": criteria.id,
        "description": criteria.description,
        "review_criteria_type": criteria.review_criteria_type,
        "options": criteria.options,
        "scores_count": scores_count,
        "can_delete": scores_count == 0,
        "delete_blockers": delete_blockers,
    }
