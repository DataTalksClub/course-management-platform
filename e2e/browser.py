"""Browser-side helpers built on Playwright sync API.

Covers the user-facing flows the suite must validate through real pages:
admin login form, django-loginas impersonation, homework submission, project
submission, and reading rendered dashboards/leaderboards.

All selectors use stable ``name``/``id`` attributes confirmed from the Django
views and templates, not brittle text matching.
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def course_row_matches(row_text: str, slug: str, title: str | None = None) -> bool:
    needle = title or slug
    return needle in row_text or slug in row_text


def course_pk_from_href(href: str) -> int | None:
    match = re.search(r"/admin/courses/course/(\d+)/change/", href)
    if match:
        return int(match.group(1))
    return None


def course_pk_from_row(row) -> int | None:
    link = row.locator("a[href*='/admin/courses/course/']").first
    if link.count() == 0:
        return None
    return course_pk_from_href(link.get_attribute("href") or "")


def indexed_values(values, limit):
    pairs = []
    if not values:
        return pairs
    for index, value in enumerate(values):
        if index >= limit:
            break
        pairs.append((index, value))
    return pairs


class AdminSession:
    """Drives an authenticated admin browser session.

    Login is via the Django admin form (``/admin/login/``) -- never OAuth.
    Impersonation uses django-loginas (``POST /admin/login/user/<id>/``).
    """

    def __init__(self, page: Page, base_url: str, ui_timeout_ms: int = 20000):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.page.set_default_timeout(ui_timeout_ms)

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def click_first_visible(self, selector: str) -> None:
        """Click the first visible element matching ``selector``.

        The site shell includes hidden submit buttons, such as the account-menu
        logout button, before admin form buttons in DOM order. Playwright's
        plain ``locator.click()`` acts on the first match even if it is hidden.
        """
        candidates = self.page.locator(selector)
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            if candidate.is_visible():
                candidate.click()
                return
        raise AssertionError(f"No visible element matched selector: {selector}")

    def submit_form_containing(self, selector: str) -> None:
        """Submit the form that owns the first element matching ``selector``."""
        field = self.page.locator(selector).first
        if field.count() == 0:
            raise AssertionError(f"No field matched selector: {selector}")
        field.evaluate(
            """(element) => {
                const form = element.form || element.closest('form');
                if (!form) {
                    throw new Error('Matched element is not inside a form');
                }
                if (form.requestSubmit) {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            }"""
        )

    # -- auth ------------------------------------------------------------
    def login_admin(self, email: str, password: str) -> None:
        self.page.goto(self.url("/admin/login/"))
        # Django admin login form: fields named username + password.
        self.page.fill("input[name='username']", email)
        self.page.fill("input[name='password']", password)
        self.page.click("input[type='submit'], button[type='submit']")
        self.page.wait_for_load_state("networkidle")
        if "/admin/login" in self.page.url:
            raise AssertionError(
                "Admin login failed: still on the login page after submitting "
                "credentials. Check E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD and "
                "that the account is staff."
            )

    def impersonate(self, user_id: int | str) -> None:
        """Switch the session to a student via django-loginas (POST + CSRF).

        We submit a real form so the CSRF cookie/token handshake works the
        same way the admin UI's "Login as user" button does.
        """
        self.page.goto(self.url(f"/admin/accounts/customuser/{user_id}/change/"))
        # The change form template includes the loginas button/form.
        loginas_button = self.page.locator(
            "button[name='login_as'], input[name='login_as'], "
            "form[action*='/admin/login/user/'] button, "
            "form[action*='/admin/login/user/'] [type='submit']"
        ).first
        if loginas_button.count() == 0:
            # Fallback: build the POST form ourselves using the CSRF cookie.
            self._impersonate_via_fetch(user_id)
            return
        loginas_button.click()
        self.page.wait_for_load_state("networkidle")

    def _impersonate_via_fetch(self, user_id: int | str) -> None:
        """Programmatic loginas POST using the session's CSRF token."""
        result = self.page.evaluate(
            """async (userId) => {
                function getCookie(name) {
                    const m = document.cookie.match(
                        new RegExp('(^|; )' + name + '=([^;]*)'));
                    return m ? decodeURIComponent(m[2]) : null;
                }
                const token = getCookie('csrftoken');
                const resp = await fetch('/admin/login/user/' + userId + '/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': token,
                              'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'csrfmiddlewaretoken=' + encodeURIComponent(token),
                    credentials: 'same-origin',
                });
                return resp.status;
            }""",
            user_id,
        )
        if result and int(result) >= 400:
            raise AssertionError(
                f"django-loginas impersonation POST returned HTTP {result} "
                f"for user {user_id}."
            )

    def stop_impersonating(self) -> None:
        self.page.evaluate(
            """async () => {
                function getCookie(name) {
                    const m = document.cookie.match(
                        new RegExp('(^|; )' + name + '=([^;]*)'));
                    return m ? decodeURIComponent(m[2]) : null;
                }
                const token = getCookie('csrftoken');
                await fetch('/accounts/stop-impersonating/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': token || ''},
                    credentials: 'same-origin',
                });
            }"""
        )
        self.page.goto(self.url("/admin/"))
        self.page.wait_for_load_state("networkidle")

    # -- test student management (admin side) ----------------------------
    def find_user_id_by_email(self, email: str) -> int | None:
        """Look up a user id via the admin changelist search.

        CustomUserAdmin has ``search_fields = ["email"]`` so the changelist
        ``?q=`` search returns matching rows; we read the edit link id.
        """
        self.page.goto(
            self.url(f"/admin/accounts/customuser/?q={email}")
        )
        self.page.wait_for_load_state("networkidle")
        link = self.page.locator(
            "a[href*='/admin/accounts/customuser/']"
        ).filter(has_text="")
        import re

        for i in range(link.count()):
            href = link.nth(i).get_attribute("href") or ""
            m = re.search(r"/admin/accounts/customuser/(\d+)/change/", href)
            if m:
                return int(m.group(1))
        return None

    def create_student(self, email: str, password: str) -> int:
        """Create a non-staff student via the admin add form.

        The deployed app currently registers CustomUser with a plain
        ModelAdmin, so the add form exposes the model's raw ``password`` field.
        Older/local variants may use UserAdmin's ``password1``/``password2``
        add form. Support both: the smoke flow impersonates the student and
        does not rely on the target user's password for login.
        """
        self.page.goto(self.url("/admin/accounts/customuser/add/"))
        self.page.wait_for_load_state("networkidle")
        self._fill_student_add_form(email, password)
        self.submit_form_containing("input[name='username']")
        self.page.wait_for_load_state("networkidle")
        self._ensure_student_email_on_change_form(email)
        user_id = self.find_user_id_by_email(email)
        if user_id is None:
            raise AssertionError(
                f"Created student {email} but could not find its user id."
            )
        return user_id

    def _fill_student_add_form(self, email: str, password: str) -> None:
        self.page.fill("input[name='username']", email)
        if self.page.locator("input[name='email']").count():
            self.page.fill("input[name='email']", email)
        self._fill_student_password_fields(password)

    def _fill_student_password_fields(self, password: str) -> None:
        if self.page.locator("input[name='password1']").count():
            self.page.fill("input[name='password1']", password)
            self.page.fill("input[name='password2']", password)
        elif self.page.locator("input[name='password']").count():
            self.page.fill("input[name='password']", password)
        else:
            raise AssertionError(
                "CustomUser admin add form did not expose password fields."
            )

    def _ensure_student_email_on_change_form(self, email: str) -> None:
        # On the resulting change form, also set the email field if present.
        if not self.page.locator("input[name='email']").count():
            return
        self.page.fill("input[name='email']", email)
        self.submit_form_containing("input[name='email']")
        self.page.wait_for_load_state("networkidle")

    def ensure_student(self, email: str, password: str) -> int:
        existing = self.find_user_id_by_email(email)
        if existing is not None:
            return existing
        return self.create_student(email, password)

    # -- course teardown (admin side) ------------------------------------
    def find_course_pk(self, slug: str, *, title: str | None = None) -> int | None:
        """Resolve a Course primary key from its slug via the admin changelist.

        ``CourseAdmin`` has no ``search_fields``, so the ``?q=`` search does
        not filter -- the changelist lists every course. We therefore walk the
        result rows and match ours by the row text (the namespaced ``slug`` is
        embedded in the title ``E2E Smoke <slug>``; we also accept an explicit
        ``title``), then read the ``<pk>`` out of that row's change link
        (``/admin/courses/course/<pk>/change/``).
        """
        self.page.goto(self.url("/admin/courses/course/"))
        self.page.wait_for_load_state("networkidle")
        # Each result row's first cell is an <a> to the change form. Find the
        # row whose visible text contains our slug/title and read its pk.
        rows = self.page.locator("#result_list tbody tr")
        for i in range(rows.count()):
            row = rows.nth(i)
            try:
                row_text = row.inner_text()
            except Exception:
                continue
            if not course_row_matches(row_text, slug, title):
                continue
            course_pk = course_pk_from_row(row)
            if course_pk is not None:
                return course_pk
        return None

    def _course_is_absent(self, slug: str) -> bool:
        return self.find_course_pk(slug) is None

    def _open_course_delete_confirmation(self, course_pk: int) -> None:
        self.page.goto(self.url(f"/admin/courses/course/{course_pk}/delete/"))
        self.page.wait_for_load_state("networkidle")

    def _submit_course_delete_confirmation(self) -> bool:
        # The confirmation page's form carries csrfmiddlewaretoken + post=yes.
        selector = "input[name='post'][value='yes']"
        if self.page.locator(selector).count() == 0:
            return False
        self.submit_form_containing(selector)
        self.page.wait_for_load_state("networkidle")
        return True

    def delete_course_via_admin(
        self,
        slug: str,
        *,
        course_pk: int | None = None,
    ) -> bool:
        """Delete a Course (and its cascade) through the Django admin UI.

        Opens the admin delete-confirmation page
        (``/admin/courses/course/<pk>/delete/``) and submits the "Yes, I'm
        sure" form (which carries the CSRF token + ``post=yes``). Deleting the
        Course cascades to all test data (homeworks, questions, projects,
        submissions, answers, enrollments, peer reviews) because every FK back
        to Course/Project is ``on_delete=CASCADE``.

        This is the deliberate cleanup path: the platform intentionally has no
        course DELETE API endpoint (a standing delete capability is unsafe), so
        teardown reuses the interactive, staff-gated admin confirmation screen.

        Returns ``True`` if the course is gone afterwards (change page 404s and
        the changelist no longer lists it), ``False`` otherwise. Never raises.
        """
        try:
            pk = course_pk
            if pk is None:
                pk = self.find_course_pk(slug)
            if pk is None:
                return self._course_is_absent(slug)

            self._open_course_delete_confirmation(pk)
            self._submit_course_delete_confirmation()
            return self._course_is_absent(slug)
        except Exception:
            return False

    # -- homework flow ---------------------------------------------------
    def _check_homework_checkboxes(self, field: str, value: str) -> None:
        indexes = str(value).split(",")
        for idx in indexes:
            idx = idx.strip()
            checkbox = self.page.locator(
                f"input[name='{field}'][type='checkbox'][value='{idx}']"
            )
            if checkbox.count() > 0:
                checkbox.first.check()

    def _fill_homework_answer(self, question_id: int, value: str) -> None:
        field = f"answer_{question_id}"
        radios = self.page.locator(
            f"input[name='{field}'][type='radio'][value='{value}']"
        )
        checkboxes = self.page.locator(
            f"input[name='{field}'][type='checkbox']"
        )

        if radios.count() > 0:
            radios.first.check()
        elif checkboxes.count() > 0:
            self._check_homework_checkboxes(field, value)
        else:
            self.page.fill(f"[name='{field}']", str(value))

    def _fill_optional_homework_field(
        self,
        selector: str,
        value: str | float | None,
    ) -> None:
        if value is not None and self.page.locator(selector).count():
            self.page.fill(selector, str(value))

    def _fill_learning_in_public_links(self, links: list[str] | None) -> None:
        inputs = self.page.locator("[name='learning_in_public_links[]']")
        link_values = indexed_values(links, inputs.count())
        for index, link in link_values:
            inputs.nth(index).fill(link)

    def _homework_submit_selector(self, answers: dict[int, str]) -> str:
        first_answer_selector = f"[name='answer_{next(iter(answers))}']"
        return (
            f"form:has({first_answer_selector}) #submit-button, "
            f"form:has({first_answer_selector}) button[type='submit'], "
            f"form:has({first_answer_selector}) input[type='submit']"
        )

    def submit_homework(
        self,
        course_slug: str,
        homework_slug: str,
        answers: dict[int, str],
        *,
        homework_url: str | None = None,
        learning_in_public_links: list[str] | None = None,
        time_spent_lectures: float | None = None,
        time_spent_homework: float | None = None,
    ) -> None:
        page = self.page
        page.goto(self.url(f"/{course_slug}/homework/{homework_slug}"))
        page.wait_for_load_state("networkidle")

        self._fill_homework_form(
            answers,
            homework_url=homework_url,
            learning_in_public_links=learning_in_public_links,
            time_spent_lectures=time_spent_lectures,
            time_spent_homework=time_spent_homework,
        )
        self.click_first_visible(self._homework_submit_selector(answers))
        page.wait_for_load_state("networkidle")

    def _fill_homework_form(
        self,
        answers: dict[int, str],
        *,
        homework_url: str | None,
        learning_in_public_links: list[str] | None,
        time_spent_lectures: float | None,
        time_spent_homework: float | None,
    ) -> None:
        for question_id, value in answers.items():
            self._fill_homework_answer(question_id, value)

        self._fill_optional_homework_field("[name='homework_url']", homework_url)
        self._fill_optional_homework_field(
            "[name='time_spent_lectures']",
            time_spent_lectures,
        )
        self._fill_optional_homework_field(
            "[name='time_spent_homework']",
            time_spent_homework,
        )
        self._fill_learning_in_public_links(learning_in_public_links)

    def homework_confirmation_text(self) -> str:
        return self.page.locator("body").inner_text()

    # -- project flow ----------------------------------------------------
    def submit_project(
        self,
        course_slug: str,
        project_slug: str,
        *,
        github_link: str,
        commit_id: str,
        certificate_name: str | None = None,
        time_spent: float | None = None,
        learning_in_public_links: list[str] | None = None,
    ) -> None:
        page = self.page
        page.goto(self.url(f"/{course_slug}/project/{project_slug}"))
        page.wait_for_load_state("networkidle")

        self._fill_project_required_fields(github_link, commit_id)
        self._fill_optional_project_field(
            "[name='certificate_name']",
            certificate_name,
        )
        self._fill_optional_project_field("[name='time_spent']", time_spent)
        self._fill_project_learning_links(learning_in_public_links)

        page.click("#project-form button[type='submit'], "
                   "#project-form input[type='submit']")
        page.wait_for_load_state("networkidle")

    def _fill_project_required_fields(
        self,
        github_link: str,
        commit_id: str,
    ) -> None:
        self.page.fill("[name='github_link']", github_link)
        self.page.fill("[name='commit_id']", commit_id)

    def _fill_optional_project_field(self, selector: str, value) -> None:
        if value is not None and self.page.locator(selector).count():
            self.page.fill(selector, str(value))

    def _fill_project_learning_links(
        self,
        learning_in_public_links: list[str] | None,
    ) -> None:
        inputs = self.page.locator("[name='learning_in_public_links[]']")
        link_values = indexed_values(
            learning_in_public_links,
            inputs.count(),
        )
        for index, link in link_values:
            inputs.nth(index).fill(link)

    def delete_project_submission(self, course_slug: str, project_slug: str) -> None:
        """Delete the impersonated student's own project submission via the UI.

        The project view accepts ``action=delete`` on POST. We post it with
        the page CSRF token. This is the only remote way to remove a
        submission so the project becomes deletable again.
        """
        page = self.page
        page.goto(self.url(f"/{course_slug}/project/{project_slug}"))
        page.evaluate(
            """async () => {
                function getCookie(name) {
                    const m = document.cookie.match(
                        new RegExp('(^|; )' + name + '=([^;]*)'));
                    return m ? decodeURIComponent(m[2]) : null;
                }
                const token = getCookie('csrftoken');
                await fetch(window.location.pathname, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'csrfmiddlewaretoken=' + encodeURIComponent(token) +
                          '&action=delete',
                    credentials: 'same-origin',
                });
            }"""
        )

    # -- read-only pages -------------------------------------------------
    def open(self, path: str) -> str:
        self.page.goto(self.url(path))
        self.page.wait_for_load_state("networkidle")
        return self.page.locator("body").inner_text()

    def expect_redirect_to_login(self, path: str) -> None:
        self.page.goto(self.url(path))
        expect(self.page).to_have_url(
            __import__("re").compile(r"/login(/|\?|$)")
        )
