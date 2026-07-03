def annotated_or_count(obj, annotated_attr, manager_name):
    """Return a Count annotation if the queryset provided one, else query.

    List endpoints annotate related counts so serializing N rows stays a
    single query. Single-object responses (create/update) don't annotate,
    so we fall back to the reverse manager's ``.count()`` (one row, one
    query).
    """
    value = getattr(obj, annotated_attr, None)
    if value is not None:
        return value
    return getattr(obj, manager_name).count()
