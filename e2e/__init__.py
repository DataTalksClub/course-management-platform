"""End-to-end smoke test suite for the Course Management Platform.

This package hits a *live* deployment (dev by default) and is intentionally
kept out of the Django unit-test suite (``courses/tests`` etc.). It is run
with its own pytest config under ``e2e/`` so it never touches the project
database or the regular test run.
"""
