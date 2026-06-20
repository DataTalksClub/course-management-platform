"""Browser-side helpers built on Playwright sync API.

Covers the user-facing flows the suite must validate through real pages:
admin login form, django-loginas impersonation, homework submission, project
submission, and reading rendered dashboards/leaderboards.

All selectors use stable ``name``/``id`` attributes confirmed from the Django
views and templates, not brittle text matching.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


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

        The CustomUser add form (AbstractUser) asks for username + the two
        password fields. Username is set to the email so login/lookup work.
        """
        self.page.goto(self.url("/admin/accounts/customuser/add/"))
        self.page.wait_for_load_state("networkidle")
        self.page.fill("input[name='username']", email)
        self.page.fill("input[name='password1']", password)
        self.page.fill("input[name='password2']", password)
        self.page.click("input[name='_save'], button[type='submit'], "
                        "input[type='submit']")
        self.page.wait_for_load_state("networkidle")
        # On the resulting change form, also set the email field if present.
        if self.page.locator("input[name='email']").count():
            self.page.fill("input[name='email']", email)
            self.page.click("input[name='_save'], button[type='submit'], "
                            "input[type='submit']")
            self.page.wait_for_load_state("networkidle")
        user_id = self.find_user_id_by_email(email)
        if user_id is None:
            raise AssertionError(
                f"Created student {email} but could not find its user id."
            )
        return user_id

    def ensure_student(self, email: str, password: str) -> int:
        existing = self.find_user_id_by_email(email)
        if existing is not None:
            return existing
        return self.create_student(email, password)

    # -- homework flow ---------------------------------------------------
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

        for question_id, value in answers.items():
            field = f"answer_{question_id}"
            # Radio (MC) / checkbox (CB): value is the 1-based option index.
            radios = page.locator(
                f"input[name='{field}'][type='radio'][value='{value}']"
            )
            checkboxes = page.locator(
                f"input[name='{field}'][type='checkbox']"
            )
            if radios.count() > 0:
                radios.first.check()
            elif checkboxes.count() > 0:
                for idx in str(value).split(","):
                    idx = idx.strip()
                    cb = page.locator(
                        f"input[name='{field}'][type='checkbox'][value='{idx}']"
                    )
                    if cb.count() > 0:
                        cb.first.check()
            else:
                # Free-form text / textarea.
                page.fill(f"[name='{field}']", str(value))

        if homework_url is not None and page.locator(
            "[name='homework_url']"
        ).count():
            page.fill("[name='homework_url']", homework_url)
        if time_spent_lectures is not None and page.locator(
            "[name='time_spent_lectures']"
        ).count():
            page.fill("[name='time_spent_lectures']", str(time_spent_lectures))
        if time_spent_homework is not None and page.locator(
            "[name='time_spent_homework']"
        ).count():
            page.fill("[name='time_spent_homework']", str(time_spent_homework))
        if learning_in_public_links:
            inputs = page.locator("[name='learning_in_public_links[]']")
            for i, link in enumerate(learning_in_public_links):
                if i < inputs.count():
                    inputs.nth(i).fill(link)

        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_load_state("networkidle")

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

        page.fill("[name='github_link']", github_link)
        page.fill("[name='commit_id']", commit_id)
        if certificate_name is not None and page.locator(
            "[name='certificate_name']"
        ).count():
            page.fill("[name='certificate_name']", certificate_name)
        if time_spent is not None and page.locator("[name='time_spent']").count():
            page.fill("[name='time_spent']", str(time_spent))
        if learning_in_public_links:
            inputs = page.locator("[name='learning_in_public_links[]']")
            for i, link in enumerate(learning_in_public_links):
                if i < inputs.count():
                    inputs.nth(i).fill(link)

        page.click("#project-form button[type='submit'], "
                   "#project-form input[type='submit']")
        page.wait_for_load_state("networkidle")

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
