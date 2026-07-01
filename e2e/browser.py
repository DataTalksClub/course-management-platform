"""Browser-side helpers built on Playwright sync API.

Covers the user-facing flows the suite must validate through real pages:
admin login form, django-loginas impersonation, homework submission, project
submission, and reading rendered dashboards/leaderboards.

All selectors use stable ``name``/``id`` attributes confirmed from the Django
views and templates, not brittle text matching.
"""

import re
from dataclasses import dataclass

from playwright.sync_api import Page, expect


@dataclass(frozen=True)
class HomeworkSubmissionData:
    course_slug: str
    homework_slug: str
    answers: dict[int, str]
    homework_url: str | None = None
    learning_in_public_links: list[str] | None = None
    time_spent_lectures: float | None = None
    time_spent_homework: float | None = None


@dataclass(frozen=True)
class ProjectSubmissionData:
    course_slug: str
    project_slug: str
    github_link: str
    commit_id: str
    certificate_name: str | None = None
    time_spent: float | None = None
    learning_in_public_links: list[str] | None = None


def course_row_matches(row_text: str, slug: str, title: str | None = None) -> bool:
    if title:
        needle = title
    else:
        needle = slug
    needle_matches = needle in row_text
    slug_matches = slug in row_text
    if needle_matches:
        return True
    return slug_matches


def course_pk_from_href(href: str) -> int | None:
    match = re.search(r"/admin/courses/course/(\d+)/change/", href)
    if match:
        pk_text = match.group(1)
        course_pk = int(pk_text)
        return course_pk
    return None


def course_pk_from_row(row) -> int | None:
    link = row.locator("a[href*='/admin/courses/course/']").first
    if link.count() == 0:
        return None
    href = link.get_attribute("href") or ""
    course_pk = course_pk_from_href(href)
    return course_pk


def indexed_values(values, limit):
    pairs = []
    if not values:
        return pairs
    for index, value in enumerate(values):
        if index >= limit:
            break
        pair = (index, value)
        pairs.append(pair)
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
        candidate_count = candidates.count()
        for index in range(candidate_count):
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
        login_url = self.url("/admin/login/")
        self.page.goto(login_url)
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
        user_change_url = self.url(
            f"/admin/accounts/customuser/{user_id}/change/"
        )
        self.page.goto(user_change_url)
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
        admin_url = self.url("/admin/")
        self.page.goto(admin_url)
        self.page.wait_for_load_state("networkidle")

    # -- test student management (admin side) ----------------------------
    def find_user_id_by_email(self, email: str) -> int | None:
        """Look up a user id via the admin changelist search.

        CustomUserAdmin has ``search_fields = ["email"]`` so the changelist
        ``?q=`` search returns matching rows; we read the edit link id.
        """
        user_search_url = self.url(f"/admin/accounts/customuser/?q={email}")
        self.page.goto(user_search_url)
        self.page.wait_for_load_state("networkidle")
        link = self.page.locator(
            "a[href*='/admin/accounts/customuser/']"
        ).filter(has_text="")

        link_count = link.count()
        for i in range(link_count):
            href = link.nth(i).get_attribute("href") or ""
            m = re.search(r"/admin/accounts/customuser/(\d+)/change/", href)
            if m:
                user_id_text = m.group(1)
                user_id = int(user_id_text)
                return user_id
        return None

    def create_student(self, email: str, password: str) -> int:
        """Create a non-staff student via the admin add form.

        The deployed app currently registers CustomUser with a plain
        ModelAdmin, so the add form exposes the model's raw ``password`` field.
        Older/local variants may use UserAdmin's ``password1``/``password2``
        add form. Support both: the smoke flow impersonates the student and
        does not rely on the target user's password for login.
        """
        user_add_url = self.url("/admin/accounts/customuser/add/")
        self.page.goto(user_add_url)
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
        course_list_url = self.url("/admin/courses/course/")
        self.page.goto(course_list_url)
        self.page.wait_for_load_state("networkidle")
        # Each result row's first cell is an <a> to the change form. Find the
        # row whose visible text contains our slug/title and read its pk.
        rows = self.page.locator("#result_list tbody tr")
        row_count = rows.count()
        for i in range(row_count):
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

    def _open_course_delete_confirmation(self, course_pk: int) -> None:
        delete_url = self.url(f"/admin/courses/course/{course_pk}/delete/")
        self.page.goto(delete_url)
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

        The platform intentionally has no course DELETE API endpoint, so e2e
        teardown uses the staff-gated admin confirmation screen. Returns
        ``True`` if the course is gone afterwards, ``False`` otherwise.
        """
        try:
            pk = course_pk
            if pk is None:
                pk = self.find_course_pk(slug)
            if pk is None:
                return self.find_course_pk(slug) is None

            self._open_course_delete_confirmation(pk)
            self._submit_course_delete_confirmation()
            return self.find_course_pk(slug) is None
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
        input_count = inputs.count()
        link_values = indexed_values(links, input_count)
        for index, link in link_values:
            inputs.nth(index).fill(link)

    def _homework_submit_selector(self, answers: dict[int, str]) -> str:
        answer_ids = iter(answers)
        first_answer_id = next(answer_ids)
        first_answer_selector = f"[name='answer_{first_answer_id}']"
        return (
            f"form:has({first_answer_selector}) #submit-button, "
            f"form:has({first_answer_selector}) button[type='submit'], "
            f"form:has({first_answer_selector}) input[type='submit']"
        )

    def submit_homework(self, data: HomeworkSubmissionData) -> None:
        page = self.page
        homework_url = self.url(
            f"/{data.course_slug}/homework/{data.homework_slug}"
        )
        page.goto(homework_url)
        page.wait_for_load_state("networkidle")

        self._fill_homework_form(data)
        submit_selector = self._homework_submit_selector(data.answers)
        self.click_first_visible(submit_selector)
        page.wait_for_load_state("networkidle")

    def _fill_homework_form(self, data: HomeworkSubmissionData) -> None:
        for question_id, value in data.answers.items():
            self._fill_homework_answer(question_id, value)

        self._fill_optional_homework_field(
            "[name='homework_url']",
            data.homework_url,
        )
        self._fill_optional_homework_field(
            "[name='time_spent_lectures']",
            data.time_spent_lectures,
        )
        self._fill_optional_homework_field(
            "[name='time_spent_homework']",
            data.time_spent_homework,
        )
        self._fill_learning_in_public_links(data.learning_in_public_links)

    def homework_confirmation_text(self) -> str:
        body = self.page.locator("body")
        body_text = body.inner_text()
        return body_text

    # -- project flow ----------------------------------------------------
    def submit_project(self, data: ProjectSubmissionData) -> None:
        page = self.page
        project_url = self.url(
            f"/{data.course_slug}/project/{data.project_slug}"
        )
        page.goto(project_url)
        page.wait_for_load_state("networkidle")

        self._fill_project_required_fields(data.github_link, data.commit_id)
        self._fill_optional_project_field(
            "[name='certificate_name']",
            data.certificate_name,
        )
        self._fill_optional_project_field("[name='time_spent']", data.time_spent)
        self._fill_project_learning_links(data.learning_in_public_links)

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
        input_count = inputs.count()
        link_values = indexed_values(
            learning_in_public_links,
            input_count,
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
        project_url = self.url(f"/{course_slug}/project/{project_slug}")
        page.goto(project_url)
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
        target_url = self.url(path)
        self.page.goto(target_url)
        self.page.wait_for_load_state("networkidle")
        body = self.page.locator("body")
        body_text = body.inner_text()
        return body_text

    def expect_redirect_to_login(self, path: str) -> None:
        target_url = self.url(path)
        self.page.goto(target_url)
        login_url_pattern = re.compile(r"/login(/|\?|$)")
        expect(self.page).to_have_url(login_url_pattern)
