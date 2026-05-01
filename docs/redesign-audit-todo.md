# Redesign Audit TODO

Scope: UI/UX fixes only. Do not add migrations or change the database schema.

## Should Fix

- [x] Course desktop: widen or stabilize the deadline column so dates do not wrap awkwardly.
- [x] Course mobile: replace or remove the `Download Certificate` icon because it reads as a dark blob on Pixel 7.
- [x] Cadmin mobile: mute repeated utility links (`Public`, `Django`, `Submissions`) further so titles remain the dominant links.
- [x] Cadmin rows: normalize the `Score` action styling so green text inside a neutral button does not look inconsistent.
- [x] Homework scored page: convert read-only submission values from input-shaped boxes into definition-style rows.
- [x] Course demo data: resolve titles like `Upcoming HW...` showing `Deadline passed`, or avoid relative urgency wording in titles.
- [x] Breadcrumbs: show the full breadcrumb trail on mobile instead of collapsing to only the last page.
- [x] Breadcrumbs: remove the redundant `Home / Courses` prefix; course-platform pages should start with the course name.
- [x] Homework statistics: replace card/pill-heavy layout with a clearer report/table structure.
- [x] Course dashboard: make homework/project metrics easier to scan than current small mobile pills.
- [x] Breadcrumbs: audit all action pages, including leaderboard statistics, and ensure the full action path is reflected.

## Polish

- [x] Enrollment mobile: reduce section spacing slightly and keep helper text closer to its field.
- [x] Footer mobile: make the `Version: N/A` pill quieter.
- [x] Enrollment page: make `Certificate: Not available` quieter supporting metadata.
- [x] Dense lists: keep title links strong and utility links muted until hover.
- [x] Cadmin submissions: continue improving mobile and desktop readability after the first table/detail pass.
- [x] Production-like demo data: review captured production content locally and tune placeholders if needed.
- [x] Course list imagery: remove placeholder thumbnail blocks unless real course assets are introduced later.

## Verification Checklist

- [x] Capture Pixel 7 screenshots for course page, cadmin course page, enrollment, and scored homework.
- [x] Capture desktop screenshots for course page and cadmin course page.
- [x] Confirm no dark blocks appear in light mode.
- [x] Confirm no horizontal overflow on Pixel 7.
- [x] Confirm dates render in local time, not raw ISO strings.
- [x] Run `git diff --check`.
- [x] Run `uv run python manage.py makemigrations --check --dry-run`.
- [x] Run the focused Django tests for course, homework, and cadmin views.
