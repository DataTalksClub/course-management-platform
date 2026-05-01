# Redesign Audit TODO

Scope: UI/UX fixes only. Do not add migrations or change the database schema.

## CAdmin / Studio UX Audit

Admin users are usually trying to answer operational questions, not browse raw
database objects. The CAdmin course page should therefore prioritize what needs
attention before showing complete homework, project, and enrollment lists.

### Admin Scenarios

- [x] List the main admin scenarios and current friction.
- [x] Evaluate difficulty for course status, scoring, project reviews, student
  support, submission review, and Learning in Public workflows.
- [x] Rearrange the CAdmin course page around task-oriented sections.
- [x] Add an at-a-glance "Needs attention" area for scoring, project review
  assignment, and project scoring.
- [x] Move student-support entry points higher on the page.
- [x] Make high-impact maintenance actions explicit instead of terse row labels.
- [x] Keep full Homework and Projects lists, but make them secondary to the
  operational summary.
- [x] Improve CAdmin enrollments with task filters for LiP disabled, zero score,
  hidden from leaderboard, and missing submissions.
- [x] Improve homework submissions with server-side search and pagination for
  staff correction workflows.
- [x] Improve project submissions with filters for incomplete reviews, missing
  repository, unscored records, and failed/not-passed status.

### Scenario Difficulty

| Scenario | Current difficulty | Reason |
| --- | --- | --- |
| Understand course operational status | Hard | The landing page lists everything, but does not answer what needs attention now. |
| Score or re-score homework | Medium | Actions exist, but are repeated per row and the labels are too terse. |
| Set correct answers | Hard/risky | `Answers` is unclear and looks like a normal action despite changing scoring behavior. |
| Manage project review flow | Medium-hard | Assigning reviews and scoring are buried in the full project list. |
| Find and help a student | Hard | Enrollments has many records, limited filters, and support actions are not grouped by task. |
| Investigate homework submissions | Medium | Staff mainly need fast search, pagination, and direct edit access for correction requests. |
| Investigate project submissions | Medium | Useful columns exist, but action/status filters are missing. |
| Inspect or disable Learning in Public | Hard | Important workflow is buried in enrollment edit. |
| Open public/admin surfaces | Easy | Course page, dashboard, leaderboard, and Django Admin links are visible. |

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
