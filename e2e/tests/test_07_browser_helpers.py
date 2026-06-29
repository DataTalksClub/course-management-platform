from e2e.browser import course_pk_from_href, course_row_matches, indexed_values


def test_course_row_matches_slug_or_title():
    assert course_row_matches("E2E Smoke e2e-smoke-123", "e2e-smoke-123")
    assert course_row_matches("Visible course title", "slug", "Visible course")
    assert not course_row_matches("Different course", "e2e-smoke-123")


def test_course_pk_from_admin_href():
    assert course_pk_from_href("/admin/courses/course/42/change/") == 42
    assert course_pk_from_href("/admin/courses/homework/42/change/") is None


def test_indexed_values_respects_input_limit():
    assert indexed_values(["a", "b", "c"], 2) == [(0, "a"), (1, "b")]
    assert indexed_values([], 2) == []
    assert indexed_values(None, 2) == []
