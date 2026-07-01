# Refactoring Plan

Created: 2026-06-28
Updated: 2026-07-01

This plan captures the current code-structure findings and a staged path for
simplifying the codebase without changing user-visible behavior. The goal is to
reduce long view functions, clarify API ownership, and move business logic into
testable service functions.

## Ground Rules

- Keep public URLs, route names, response shapes, and templates stable unless a
  step explicitly says otherwise.
- Prefer small behavior-preserving moves before changing internals.
- Add focused tests around extracted services before or during each refactor.
- Use `uv run python manage.py test ...` for Django tests.
- Do not mix UI redesign with backend refactoring unless a step specifically
  touches templates or form behavior.
- Do not introduce list/dict/set comprehensions during cleanup. Prefer explicit
  loops so filtering, appending, and early exits stay easy to inspect.
- Use Pyrefly as a whole-repo Python type check during cleanup.
- Do not add trivial pass-through functions. Extract helpers only when they
  name a real concept, isolate non-trivial branching, or make repeated behavior
  safer.
- Do not inline constructed values inside `append(...)`. Assign the dictionary,
  object, or function result to a named local variable first, then append it.
- Avoid compact `sum(...)`/`next(...)` generator expressions when they include
  filtering, branching, or non-trivial construction. Use an explicit loop with a
  named counter/result instead.
- Use direct `range(...)`, `zip(...)`, `enumerate(...)`, and `.items()` in `for`
  loops when they are the clearest Python expression. Do not create one-off
  aliases such as `indexes = range(...)` or `pairs = zip(...)` just to satisfy
  a cleanup rule. The same applies to simple enum/class/queryset attributes
  used only by the next loop, such as `statuses = DatamailerOutboxStatus.values`;
  use `for status in DatamailerOutboxStatus.values:` directly.
- Prefer direct imports from the real owner module. Do not keep compatibility
  re-export modules or fallback import shims after internal callers have moved.
- Tuple unpacking with one or two values is fine. When a loop unpacks three or
  more positional values, prefer a named structure such as a dataclass, named
  tuple, small object, or explicit dictionary keys so field meaning is visible
  at the use site.
- Treat long parameter lists as a smell, especially when the same values travel
  through several functions together. Introduce a named dataclass or value
  object for that group, then pass the object directly instead of unpacking it
  back into many arguments.
- As a working threshold, pause when an internal function needs five or more
  arguments. Either split responsibilities or group the values into a named
  request/context/result object. Keyword-only arguments make calls clearer, but
  they do not by themselves fix the smell.
- When a dataclass or value object replaces a group of arguments, let downstream
  functions accept that object when they operate on the same concept. Do not
  immediately expand `data.field_one`, `data.field_two`, and so on into another
  long call unless the called API is an external/framework boundary.
- In general, avoid hiding non-trivial work inside inline expressions during
  cleanup. Prefer named intermediate variables for constructed records,
  counters, querysets with filtering/annotations, and other values whose purpose
  is not obvious from the immediate expression.
- Do not inline meaningful function calls inside dataclass, model, or dictionary
  construction. Assign the result to a named local first, then pass the local
  into the constructor or record.
- Do not inline meaningful function calls inside tuple/list record construction.
  Assign the value to a named local first, then build the tuple/list record.
- Do not nest meaningful function calls as arguments to other function calls.
  Assign the inner result to a named local first so each step has a visible
  purpose.
- Do not inline context-builder calls inside `render(...)`. Assign
  `context = some_context_builder(...)` first, then pass `context` to `render`.
- When a set of related flat modules shares a strong prefix and one public
  entry point, prefer a package. For example, move `openapi_*` modules under
  `openapi/`, or `payloads_*` modules under `payloads/`, while keeping the
  public import path stable through `__init__.py`.
- Move large static data tables out of Python modules into readable config/data
  files when the Python code only needs to parse and consume the data. Keep the
  parser explicit and covered by focused tests.
- After extracting helpers or value objects, do a cleanup pass for leftovers.
  Remove wrappers that now only forward to another function, add a one-line
  guard, or group only one or two obvious arguments without naming a durable
  domain concept.

## Progress Log

- [x] Split scored homework result view tests out of the oversized homework
  detail test module.
- [x] Replace remaining large tuple unpacking in project statistics tests with
  named values or a dataclass.
- [x] Split optional homework submission-field tests out of the oversized
  homework detail test module.
- [x] Split all-project-submissions course page tests out of the oversized
  course detail test module.
- [x] Split project statistics admin-action tests out of the oversized project
  statistics test module.
- [x] Split homework submission validation tests out of the oversized homework
  detail test module.
- [x] Split dashboard integration and authentication tests out of the oversized
  dashboard test module.
- [x] Split course duplication admin tests out of the oversized course detail
  test module.
- [x] Split project list view tests out of the oversized project evaluation
  test module.
- [x] Extract deadline reminder event planning from the management command into
  a focused `courses.deadline_reminder_events` module.
- [x] Split deadline reminder planning helpers by responsibility into type,
  member, query, and event modules.
- [x] Split API homework list/create serialization helpers out of the oversized
  homework API view module.
- [x] Split API homework upsert validation and save flow out of the public
  homework API view module.
- [x] Split API project list/create serialization helpers out of the oversized
  project API view module.
- [x] Split API project upsert validation and save flow out of the public
  project API view module.
- [x] Split API project score and assign-review response helpers out of the
  public project API view module.
- [x] Split cadmin registration-campaign Datamailer action helpers out of the
  public campaign page view module.
- [x] Split public homework POST preview and validation-error context helpers
  out of the homework detail view module.
- [x] Rename the generic `courses.projects` scoring module to
  `courses.project_scoring` and update direct imports without a compatibility
  shim.
- [x] Split Datamailer homework/project submission recipient-list payload
  helpers out of the shared payload base module.
- [x] Split Datamailer registration campaign, confirmation, contact, and
  recipient-list payload helpers out of the shared payload base module.
- [x] Split Datamailer project-passed outcome recipient-list payload helpers
  out of the score-notification payload module.
- [x] Split project score calculation and peer-review grouping helpers out of
  the project scoring orchestration module.
- [x] Split homework answer correctness and single-submission score update
  helpers out of the homework scoring orchestration module.
- [x] Split Datamailer recipient-list source querysets and batch assembly out
  of the sync management command into a shared batch module.
- [x] Split Datamailer recipient-list import JSONL/S3 upload helpers out of
  the sync management command.
- [x] Split public project submissions view support into focused listing,
  viewer-state, display-decoration, and voting modules while keeping the
  route-level view module thin.
- [x] Split enrollment export API ownership into direct graduates and
  certificate-update view modules without a compatibility re-export.
- [x] Split the public project detail view into route handling, page-context,
  and submission-edit modules so the view module only coordinates responses.
- [x] Split homework upsert API internals into shared rules, validation,
  question replacement, and persistence modules while keeping the public
  upsert view module as the coordinator.
- [x] Split course homepage display metadata out of the public course list view
  so list and detail pages share it through a direct owner module.
- [x] Split course API serialization and mutation workflows out of the public
  course API view module, keeping list/detail handlers as coordinators.
- [x] Split dashboard metric calculation into common metric, homework,
  project, and context modules, leaving the dashboard view as the route/render
  boundary.
- [x] Split project evaluation submit context decoration and review persistence
  out of the route-level submit view.
- [x] Split cached course leaderboard data and score-breakdown query helpers
  out of the leaderboard view module.
- [x] Split registration campaign API serialization, mutation, and
  registration-list helpers out of the public API view module.
- [x] Split cadmin homework submission listing/search and submission edit
  helpers out of the homework admin action module.
- [x] Split cadmin campaign form/edit, metrics, and registration-list helpers
  out of the public campaign route module.
- [x] Split cadmin project submission listing and edit helpers out of the
  project admin action module while preserving notification patch points.
- [x] Split cadmin Datamailer operations-dashboard and events-list helpers out
  of the route module.
- [x] Split cadmin enrollment list, leaderboard complaint, and enrollment edit
  helpers out of the route module.
- [x] Split public course project query and badge decoration helpers out of
  the course route/context module.
- [x] Split project submission confirmation field and context builders out of
  the email delivery module.
- [x] Split public course registration form and profile-sync helpers out of
  the generic course view forms module.
- [x] Split API certificate update validation, persistence, and notification
  queuing out of the route module while preserving the notification patch path.
- [x] Split API leaderboard export queryset, pagination, and serialization
  helpers out of the YAML/cache route module.
- [x] Split API question serialization and mutation helpers out of the route
  module.
- [x] Split repeated API project action staff-check and lookup coordination
  into a shared route helper.
- [x] Flatten Datamailer membership sync payload construction and remove unused
  internal dataclass fields.
- [x] Flatten duplicate-course admin creation inputs and clean criteria form
  validation style.
- [x] Flatten Datamailer outbox timestamp and response payload construction in
  enqueue/dispatch status updates.
- [x] Split project POST delete/save branches out of the public project view
  coordinator.
- [x] Split homework statistics scored/unscored response paths out of the
  public statistics view coordinator.
- [x] Split unauthorized peer-review submit response out of the public
  evaluation submit view coordinator.
- [x] Split peer-review submit save-and-redirect response out of the POST
  coordinator.
- [x] Split leaderboard complaint form context construction out of the public
  complaint view coordinator.
- [x] Split optional peer-review creation and self-review guard out of the
  public project-evaluation add route.
- [x] Split API leaderboard export homework/project queryset builders out of
  the prefetch coordinator.
- [x] Replace repetitive API course-create field extraction with an explicit
  default table and value builder.
- [x] Split cadmin campaign edit POST action selection out of the public edit
  view coordinator.
- [x] Group cadmin Datamailer campaign action inputs into a value object and
  pass it through action upsert/run helpers.
- [x] Split Datamailer project-passed outcome membership add/remove branches
  out of the sync coordinator.
- [x] Split Datamailer peer-review assignment public route URL construction
  out of the assignment URL record builder.
- [x] Split Datamailer registration confirmation course context fields out of
  the confirmation context record builder.
- [x] Split long Datamailer client endpoint test case lists into endpoint-area
  groups with explicit aggregators.
- [x] Split remaining long dashboard and project-statistics test helpers into
  focused fixture/assertion or score-row groups.
- [x] Flatten compact Datamailer outbox ID extraction and recipient-list JSONL
  encoding return expressions into named intermediate steps.
- [x] Replace non-test `courses.models` compatibility re-export imports with
  direct owner-module imports across API, cadmin, Datamailer, course admin,
  course services, and course views.
- [x] Remove single-use Datamailer management-command wrappers that only
  forwarded batch construction, validation, or request-data construction.
- [x] Remove the deadline formatting alias and import the owner formatter
  directly from timezone services.
- [x] Remove the single-use peer-review assignment constructor wrapper while
  keeping assignment construction explicit before append.
- [x] Split Datamailer outbox event sender strategies out of the dispatch
  orchestration module.
- [x] Split Datamailer membership outbox event builders out of the public
  membership sync entry-point module.
- [x] Split Datamailer webhook request authentication, JSON parsing, and field
  validation out of the route/persistence module.
- [x] Split homework submission POST field application and validation helpers
  out of the submission persistence/callback module.
- [x] Remove cadmin view-model filter helpers that only forwarded to the
  generic status-filter helper.
- [x] Remove API bulk-create wrapper callables by letting the shared bulk
  helper accept route context arguments directly.
- [x] Replace deadline reminder context lambdas with named callable context
  objects.
- [x] Replace lambda-based admin, Datamailer dispatch, commit, and sort-key
  callbacks with named predicates, shared filters, and helper functions.
- [x] Replace remaining signal, submission, registration, and defaultdict
  lambdas with explicit callbacks and named/default factories.
- [x] Move Datamailer sync callers to direct owner-module imports and remove
  the sync package re-export shim.
- [x] Move Datamailer payload callers to direct owner-module imports and remove
  the payload package re-export shim.
- [x] Move OpenAPI spec building out of the package root and update callers to
  import the concrete owner module directly.
- [x] Move OpenAPI content path/schema aggregation out of package roots into
  explicit registry modules.
- [x] Move Datamailer template aggregation out of package roots into explicit
  registry modules.
- [x] Extend the no-lambda cleanup to accounts and timezone helpers with named
  sort-key functions.
- [x] Replace `courses.models` wildcard package exports with an explicit model
  export list.
- [x] Move random leaderboard display-name word lists out of Python code and
  into data files loaded by a small helper module.
- [x] Extend the no-lambda cleanup to maintained e2e and script helpers with
  named callbacks and sort keys.
- [x] Remove additional tiny pass-through helpers from account email extraction,
  homework numeric answer checks, and deadline reminder send payload assembly.
- [x] Split account authentication, toggle, and token-admin tests out of the
  oversized account settings test module.
- [x] Flatten remaining Datamailer registration, score, and peer-review payload
  dictionaries that inlined context, metadata, or tag helper calls.
- [x] Flatten additional cadmin campaign and Datamailer metadata builders that
  inlined URL, timestamp, list, or payload helper calls inside records.
- [x] Flatten campaign stats, course duplicate-field, and Datamailer send-status
  record builders and remove a tiny send-status count wrapper.
- [x] Split the mixed `accounts/views.py` module into focused account settings,
  toggle, email-preference, timezone, impersonation, login, and disabled-route
  view modules with direct URL imports.
- [x] Split Datamailer recipient-list audit drift comparison and Datamailer
  execution/repair logic out of the management command.
- [x] Split Datamailer outbox retry and error-classification policy out of the
  dispatch orchestration module.
- [x] Split project scoring peer-review grouping and submission scoring logic
  out of the public project scoring coordinator.
- [x] Split Datamailer recipient-list bulk upsert-before-send helpers out of
  membership sync ownership.
- [x] Split Datamailer peer-review assignment recipient/member metadata out of
  the notification payload builder.
- [x] Split Datamailer registration campaign payload construction out of the
  registration membership and confirmation payload module.
- [x] Split Datamailer homework/project score recipient-list member gathering
  out of the score notification payload builder.
- [x] Split Datamailer recipient-list send sync, audit, and error handling
  helpers out of notification-specific orchestration.
- [x] Split Datamailer campaign command payload construction and action
  execution out of the management command.
- [x] Split Datamailer recipient-list import job creation and polling out of
  inline recipient-list sync.

## Current Findings

### API owns public/export routes

`course_management/urls.py` mounts `api.urls` under `/api/`. The old
`data.urls` and `data.views` compatibility modules have been removed; public,
export, and webhook endpoints are owned by focused modules under `api/views/`:

- `GET /api/health/`
- `GET /api/courses/<course_slug>/course-criteria.yaml`
- `GET /api/courses/<course_slug>/leaderboard.yaml`
- `GET /api/courses/<course_slug>/homeworks/<homework_slug>/submissions`
- `GET /api/courses/<course_slug>/projects/<project_slug>/submissions`
- `GET /api/courses/<course_slug>/graduates`
- `POST /api/courses/<course_slug>/certificates`
- `POST /api/datamailer/events`

The confusing part is naming and module ownership: newer CRUD-style JSON
endpoints live in `api/views/*`, while older export and webhook endpoints live in
`data/views/*`.

### `cadmin/views.py` has the clearest long-function hotspots

Several admin views mix request parsing, validation, persistence, derived display
state, messages, redirects, and rendering:

- `homework_submission_edit`
- `project_submissions`
- `project_submission_edit`
- `enrollments_list`
- `enrollment_edit`

These should become thin HTTP handlers backed by forms, query helpers, and
service functions.

### Business logic leaks into views

The clearest example is disabling Learning in Public from `enrollment_edit`. That
view also zeroes related homework/project scores and recalculates totals. This is
domain behavior and should be a transactional service with direct tests.

### API CRUD endpoints repeat patterns

`api/views/homeworks.py` and `api/views/projects.py` repeat bulk create,
by-id/by-slug detail handling, upsert validation, state validation, date parsing,
and safe delete patterns. The duplication is manageable today, but it will make
new entity endpoints harder to add consistently.

### Reminder builders repeat one workflow

`courses/management/commands/send_deadline_reminders.py` has three similar event
builders for homework reminders, project submission reminders, and peer-review
reminders. A small spec-driven builder would make future reminder changes safer.

### Datamailer has too many responsibilities in one module

`course_management/datamailer.py` contains the HTTP client, payload builders,
recipient-list helpers, synchronization functions, and send orchestration. It is
large enough that splitting by responsibility would improve navigation and reduce
merge risk.

### Wrapped statistics are long but mostly linear

`calculate_wrapped_statistics` is a long orchestration function. It already has
some helper extraction, so it is lower priority than admin views and API module
ownership. It can still be split into fetch, aggregate, group, and persist steps.

## Target Shape

Keep the current Django app structure, but clarify responsibilities:

```text
api/
  views/
    courses.py
    homeworks.py
    projects.py
    questions.py
    registration_campaigns.py
    exports.py
    public.py
    webhooks.py
  presenters.py
  helpers.py

courses/
  services/
    enrollment_flags.py
    homework_submission.py
    project_submission.py
    project_scoring.py
    reminders.py
    wrapped.py

cadmin/
  forms.py
  views/
    __init__.py
    campaigns.py
    course_admin.py
    datamailer.py
    enrollment.py
    helpers.py
    homework.py
    projects.py
    view_models.py

course_management/
  datamailer/
    client.py
    payloads/
      __init__.py
      base.py
      certificates.py
      peer_review.py
      scores.py
      send.py
    sync/
      __init__.py
      audit.py
      memberships.py
      notifications.py
      status.py
    preferences.py

api/
  openapi/
    __init__.py
    content_paths.py
    content_schemas.py
    course_paths.py
    course_schemas.py
    data_paths.py
    integration_schemas.py
    paths.py
    primitives.py
    schemas.py
```

Rules of thumb:

- Views handle HTTP concerns only.
- Forms validate browser-submitted staff/user input.
- Services mutate domain state and own transactions.
- Presenters serialize model data for API responses.
- View-model/query helpers prepare display-only lists, counts, and flags.

## Phase 1. Clarify API Module Ownership

Status: Complete

Goal: make route ownership understandable without changing endpoint behavior.

Steps:

- [x] Move `data/views/health.py` to `api/views/public.py` or
  `api/views/health.py`.
- [x] Move `data/views/leaderboard.py`, `data/views/homework.py`,
  `data/views/project.py`, `data/views/enrollment.py`, and
  `data/views/course.py` into `api/views/exports.py` or focused modules under
  `api/views/`.
- [x] Move `data/views/datamailer.py` to `api/views/webhooks.py`.
- [x] Update imports in `data/urls.py`, or replace the `data.urls` include with
  equivalent paths in `api/urls.py`.
- [x] Keep all route names and paths stable during the move.
- [x] Remove the temporary `data/urls.py` and `data/views` compatibility
  modules after `api.urls` owns the routes directly.

Verification:

```bash
uv run python manage.py test data.tests api.tests.test_openapi
uv run python manage.py test data.tests.test_method_restrictions
uv run python manage.py test data.tests.test_leaderboard
uv run python manage.py test data.tests.test_homework data.tests.test_project data.tests.test_enrollment
uv run python manage.py test data.tests.test_datamailer_webhook
uv run python manage.py test api.tests
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

Acceptance checks:

- [x] `/api/openapi.json` still reports no undocumented routed endpoints.
- [x] All existing `/api/...` export URLs still resolve.
- [x] No import path in tests needs to patch old modules after the migration is
  complete.

## Phase 2. Extract Admin Edit Forms and Services

Status: Complete

Goal: reduce `cadmin/views.py` complexity for staff edit workflows.

Steps:

- [x] Add `HomeworkSubmissionEditForm`.
- [x] Add `ProjectSubmissionEditForm`.
- [x] Move POST parsing and integer validation out of
  `homework_submission_edit`.
- [x] Move POST parsing and integer validation out of
  `project_submission_edit`.
- [x] Add `update_homework_submission_from_admin(submission, cleaned_data)`.
- [x] Add `update_project_submission_from_admin(submission, cleaned_data)`.
- [x] Keep message text and redirects stable.
- [x] Keep templates stable initially; only adapt field names if the form layer
  requires it.

Verification:

```bash
uv run python manage.py test cadmin.tests
uv run python manage.py test courses.tests.test_homework courses.tests.test_project_score
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

Acceptance checks:

- [x] Staff can load and submit homework submission edit pages.
- [x] Staff can load and submit project submission edit pages.
- [x] Score totals and leaderboard updates still happen when scores change.
- [x] Invalid numeric values show an error instead of partially updating
  records.

## Phase 3. Extract Enrollment Flag Domain Logic

Status: Complete

Goal: move Learning in Public score reset behavior into a tested service.

Steps:

- [x] Create `courses/services/enrollment_flags.py`.
- [x] Add a transactional function such as:

```python
def set_learning_in_public_disabled(enrollment, disabled: bool):
    ...
```

- [x] Move homework score zeroing, project score zeroing, total recalculation, and
  leaderboard update behavior into the service.
- [x] Update `cadmin.views.enrollment_edit` to call the service.
- [x] Add direct unit tests for the service with homework and project
  submissions.

Verification:

```bash
uv run python manage.py test courses.tests.test_disable_learning_in_public
uv run python manage.py test cadmin.tests
uv run python manage.py test courses.tests.test_leaderboard
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

Acceptance checks:

- [x] Disabling Learning in Public still zeroes all relevant LiP score
  components.
- [x] Re-enabling does not invent scores that need rescoring.
- [x] Enrollment total score and leaderboard ordering remain consistent.

## Phase 4. Extract Admin List Query/View-Model Helpers

Status: Complete

Goal: make admin list views mostly compose helpers and render context.

Steps:

- [x] Create `cadmin/view_models.py` or focused helpers in `cadmin/views.py`.
- [x] Extract project submission base queryset logic.
- [x] Extract project submission peer-review completion counts.
- [x] Extract project submission filter counts.
- [x] Extract project submission status filter application.
- [x] Extract enrollment base queryset logic.
- [x] Extract enrollment filter counts.
- [x] Extract enrollment support flags.
- [x] Extract enrollment status filter application.
- [x] Keep pagination and templates unchanged.

Verification:

```bash
uv run python manage.py test cadmin.tests
uv run python manage.py test courses.tests.test_project_submissions_view
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

Acceptance checks:

- [x] Search still finds records beyond the first page.
- [x] Each admin filter count matches the visible filtered result.
- [x] Pagination links preserve search and filter query parameters.

## Phase 5. Consolidate API CRUD Helpers

Status: Complete

Goal: remove repeated JSON CRUD plumbing while keeping lightweight function-based
views.

Steps:

- [x] Add helper for single-or-list payload normalization.
- [x] Add helper for bulk create response assembly.
- [x] Add helper for by-id/by-slug object lookup.
- [x] Add helper for guarded delete response.
- [x] Add helper for state/date validation wrappers around
  `apply_patch_fields`.
- [x] Apply helpers first to homework endpoints.
- [x] Apply helpers first to project endpoints.
- [x] Do not introduce Django REST Framework unless there is a separate decision
  to expand the API architecture.
- [x] Keep serializers/presenters explicit for each resource.

Verification:

```bash
uv run python manage.py test api.tests.test_homeworks
uv run python manage.py test api.tests.test_projects
uv run python manage.py test api.tests.test_questions
uv run python manage.py test api.tests.test_courses
uv run python manage.py test api.tests.test_openapi
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

Acceptance checks:

- [x] Create, bulk create, patch, put-by-slug, delete, and score endpoints keep
  the same status codes and response bodies.
- [x] OpenAPI route coverage remains complete.
- [x] Error response codes remain stable.

## Phase 6. Refactor Deadline Reminder Builders

Status: Complete

Goal: remove repeated reminder event construction without changing sends.

Steps:

- [x] Create a `ReminderSpec` dataclass in
  `courses/management/commands/send_deadline_reminders.py` or
  `courses/services/reminders.py`.
- [x] Extract deadline window selection.
- [x] Extract metadata creation.
- [x] Extract action URL creation.
- [x] Extract base context plus email copy.
- [x] Extract `ReminderEvent` assembly.
- [x] Keep the command interface unchanged.
- [x] Keep dry-run output unchanged.

Verification:

```bash
uv run python manage.py test courses.tests.test_deadline_reminders
uv run python manage.py test courses.tests.test_datamailer
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

Acceptance checks:

- [x] Homework, project submission, and peer-review reminders target the same
  members as before.
- [x] Reminder keys, list keys, metadata, idempotency keys, and template context
  are unchanged.
- [x] Dry-run behavior remains readable and side-effect free.

## Phase 7. Split Datamailer by Responsibility

Status: Complete

Goal: make Datamailer code easier to navigate and reduce risk when editing one
workflow.

Steps:

- [x] Convert `course_management/datamailer.py` into a package in small steps.
- [x] Move HTTP client and config.
- [x] Move base payload helpers.
- [x] Move recipient-list payloads.
- [x] Move transactional payloads.
- [x] Move sync/send orchestration.
- [x] Move preference helpers.
- [x] Preserve old import paths temporarily with re-exports if that reduces
  churn.
- [x] Update tests after each move.

Verification:

```bash
uv run python manage.py test courses.tests.test_datamailer
uv run python manage.py test data.tests.test_datamailer_webhook
uv run python manage.py test cadmin.tests
uv run python manage.py test courses.tests.test_deadline_reminders
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

Acceptance checks:

- [x] Existing imports still work during the transition, or all imports are
  updated in the same change.
- [x] Payloads produced by tests are byte-for-byte equivalent where tests assert
  exact dictionaries.
- [x] Outbox/audit behavior is unchanged.

## Phase 8. Split Wrapped Statistics Orchestration

Status: Complete

Goal: make wrapped statistics easier to reason about without changing the stored
statistics shape.

Steps:

- [x] Extract date window construction.
- [x] Extract activity query loading.
- [x] Extract active student/enrollment discovery.
- [x] Extract platform aggregate calculation.
- [x] Extract per-student grouping.
- [x] Extract bulk user-stat persistence.
- [x] Keep existing model writes and field names unchanged.

Verification:

```bash
uv run python manage.py test courses.tests.test_wrapped_statistics
uv run python manage.py test courses.tests.test_scoring
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

Acceptance checks:

- [x] Re-running wrapped calculation with `force=True` produces equivalent
  `WrappedStatistics` and `UserWrappedStatistics` records.
- [x] Existing leaderboard and course stats JSON shapes remain unchanged.

## Current Cleanup Batch

Status: In progress

Steps:

- [x] Split the large `cadmin/views.py` module into a `cadmin/views/` package
  by admin workflow ownership.
- [x] Move `cadmin/view_helpers.py` and `cadmin/view_models.py` into the
  `cadmin/views/` package.
- [x] Move Datamailer payload modules into `course_management/datamailer/payloads/`.
- [x] Move Datamailer sync modules into `course_management/datamailer/sync/`.
- [x] Move OpenAPI modules into `api/openapi/`.
- [x] Move registration country and top-country data into
  `courses/countries.txt`.
- [x] Split `courses/views/course.py` into focused course, calendar,
  leaderboard, enrollment, and project-submission modules.
- [x] Split `courses/views/project.py` project-eval, project-results, and
  project-statistics route groups into focused modules.
- [x] Split `courses/views/homework.py` reporting routes into homework
  statistics and submissions modules.
- [x] Split `courses/views/course.py` homework listing/enrichment into a
  focused course-homeworks module.
- [x] Split homework submission summary and confirmation-email helpers out of
  `courses/views/homework.py`, and move shared formatting helpers away from
  homework-specific modules.
- [x] Split homework submission persistence, validation, and callback
  registration out of `courses/views/homework.py`.
- [x] Split project submission confirmation payload and email helpers out of
  `courses/views/project.py`.
- [x] Split course-list homepage presentation and registration badges out of
  `courses/views/course.py`.
- [x] Split project evaluation submit/review form workflow out of
  `courses/views/project_eval.py`.
- [x] Split project peer-review assignment out of `courses/projects.py`.
- [x] Split leaderboard updates out of `courses/scoring.py` and remove
  compatibility imports for moved scoring/project helpers.
- [x] Wire project URLs directly to split view modules and remove project view
  re-export imports.
- [x] Wire course and homework URLs directly to split view modules and remove
  course/homework view re-export imports.
- [x] Wire cadmin, API, and legacy data URLs directly to split view modules and
  remove view package re-export imports.
- [x] Remove unused `data.urls` and `data.views` compatibility modules after
  confirming no internal code imports them.
- [x] Replace root `course_management.datamailer` imports with concrete
  Datamailer module imports and remove the root package re-export shim.
- [x] Replace wildcard admin/validator imports with direct module imports and
  explicit admin module registration imports.
- [x] Remove remaining nested meaningful calls from wrapped-statistics helpers.
- [x] Remove nested queryset-to-set construction from project voting helpers.
- [x] Name peer-review assignment counts, selected submissions, timestamps, and
  review-window boundaries instead of nesting calls inline.
- [x] Name assignment-statistics query rows and scoring answer normalization
  intermediates instead of nesting conversions inline.
- [x] Name project scoring link counts and submission ids instead of nesting
  length/key conversions inline.
- [x] Name dashboard querysets, quartile inputs, counts, percentages, and
  context fragments instead of nesting view calculations inline.
- [x] Name project-submission list querysets, paginator values, context ranges,
  and display-score expression parts instead of nesting calls inline.
- [x] Name project-submission voting request values, payload fields, and vote
  count query steps instead of nesting calls inline.
- [x] Name project-result scores, feedback querysets, and context values instead
  of nesting calls inline.
- [x] Name all-project-submission count filters, annotations, and queryset
  ordering steps instead of nesting calls inline.
- [x] Name course-calendar timezone, URL, escaped text, and response-body
  values instead of nesting calls inline.
- [x] Name leaderboard prefetch, ordering, cache-version, context, and homework
  state-order values instead of nesting calls inline.
- [x] Name project-result answer option parsing values before appending them.
- [x] Name wrapped-page context values and context-update payloads instead of
  nesting calls inline.
- [x] Name shared URL and submission-formatting normalization values instead of
  nesting calls inline.
- [x] Name learning-in-public project duplicate links before updating the
  duplicate-link set.
- [x] Name course-list queryset annotations and prefetch/order steps instead of
  chaining them inline.
- [x] Name registration email normalization and context presentation values
  instead of nesting calls inline.
- [x] Name project context certificate and learning-in-public flags before
  building context objects.
- [x] Name homework-submission posted time and FAQ URL values before parsing or
  validating them.
- [x] Name project-evaluation target submissions before creating optional peer
  reviews.
- [x] Name dashboard homework queryset and max-score annotation before applying
  them.
- [x] Split Datamailer signal tests out of the oversized Datamailer test module.
- [x] Split low-level Datamailer client endpoint tests out of the oversized
  Datamailer test module.
- [x] Split Datamailer campaign command tests out of the oversized Datamailer
  test module.
- [x] Split Datamailer status and preference tests out of the oversized
  Datamailer test module.
- [x] Split Datamailer contact and transactional-send tests out of the oversized
  Datamailer test module.
- [x] Move Datamailer contact backfill command tests into the contact test
  module.
- [x] Split Datamailer recipient-list backfill, audit, and import command tests
  out of the oversized Datamailer test module.
- [x] Split Datamailer recipient-list audit tests out of the recipient-list
  command test module.
- [x] Split Datamailer outbox, erase-contact, and status command tests out of
  the oversized Datamailer workflow test module.
- [x] Split Datamailer registration confirmation and registrant membership
  tests out of the oversized Datamailer workflow test module.
- [x] Split Datamailer enrollment, submission, and project-passed membership
  tests out of the oversized Datamailer workflow test module.
- [x] Split Datamailer certificate and graduate-recipient tests out of the
  oversized Datamailer workflow test module.
- [x] Split Datamailer peer-review assignment tests out of the oversized
  Datamailer workflow test module.
- [x] Split Datamailer homework-score publication tests out of the oversized
  Datamailer workflow test module.
- [x] Rename the remaining Datamailer workflow score tests to a project-score
  test module.
- [x] Split course leaderboard and score-breakdown tests out of the oversized
  course detail test module.
- [x] Split homework submissions view tests out of the oversized homework test
  module.
- [x] Split course-list tests out of the oversized course-detail test module.
- [x] Name API detail config querysets, course create fields, and Datamailer
  project-passed payload inputs instead of nesting calls inline.
- [x] Audit compatibility-style imports after package/module moves; no remaining
  production compatibility shims were found in the current pass.
- [x] Split wrapped statistics calculation into focused activity, metrics,
  persistence, and calculator modules.
- [x] Split OpenAPI content path definitions into homework, project, and
  question modules under the content-paths package.
- [x] Split OpenAPI content schemas into homework, project, question, and enum
  modules under the content-schemas package.
- [x] Split Datamailer template definitions into submission, score,
  certificate, reminder, and peer-review modules.
- [x] Split Datamailer recipient-list sync execution and import-job polling out
  of the management command into a service module.
- [x] Split deadline reminder payload, item, and spec helpers out of the event
  orchestration module.
- [x] Split Datamailer transactional sending and certificate notification sync
  out of the recipient-list notification module.
- [x] Split Datamailer client endpoint methods into contact, recipient-list,
  transactional, and campaign mixins.
- [x] Split Datamailer outbox dispatch processing and status summary out of
  the enqueue module.
- [x] Split Datamailer contact sync and contact erase helpers out of the
  membership sync module.
- [x] Split Datamailer cadmin view tests out of the oversized cadmin view test
  module.
- [x] Split leaderboard complaint cadmin view tests out of the oversized cadmin
  view test module.
- [x] Split registration campaign cadmin view tests out of the oversized cadmin
  view test module.
- [x] Split course-list and course-admin cadmin view tests out of the oversized
  cadmin view test module.
- [x] Split impersonation and login-as cadmin view tests out of the oversized
  cadmin view test module.
- [x] Split project submission and project action cadmin view tests out of the
  oversized cadmin view test module.
- [x] Rename the remaining homework cadmin view tests from the generic
  `test_views.py` module to focused homework ownership.
- [x] Run focused tests for cadmin, Datamailer, registration, and OpenAPI.
- [x] Run the full Django test suite before committing.

Verification:

```bash
uv run python manage.py check
uv run python manage.py test cadmin.tests
uv run python manage.py test courses.tests.test_datamailer api.tests.test_openapi
uv run python manage.py test courses.tests.test_registration_campaigns
uvx pyrefly check
uv run python manage.py test
git diff --check
```

## Optional Later Cleanup

These are lower priority than the phases above.

- [ ] Continue splitting long files by ownership when a file accumulates several
  related groups behind a common prefix or feature area.
- [ ] Split very large test classes into scenario-focused files after production
  code stabilizes.
- [ ] Move one-time root scripts into `scripts/` or `.tmp/` if they are not
  intended as maintained commands.
- [ ] Audit `courses/static/courses.css` for component grouping after backend
  refactors, but only when UI work is planned.
- [ ] Replace cleanup-introduced one-off loop aliases with direct loop iterables
  when the alias adds no domain meaning.
- [ ] Replace tuple/list record construction that still inlines meaningful
  function calls with named local variables.
- [ ] Move remaining large static lookup tables out of Python modules when they
  are easier to maintain as data/config files.
- [x] Add a committed Pyrefly configuration and fix or exclude current
  whole-repo blockers so `uvx pyrefly check` can become a reliable gate.
- [ ] Fix typos discovered during refactors only when touching the relevant code
  anyway, unless the typo affects API or template behavior.

## Final Verification Before Merging a Phase

Run the focused tests for the phase, then:

```bash
uv run python manage.py test
uvx pyrefly check
uv run python manage.py makemigrations --check --dry-run
git diff --check
```

If a phase touches route ownership or API responses, also run:

```bash
uv run python manage.py test api.tests.test_openapi
```

If a phase touches templates, CSS, forms, buttons, or page layout, read
`docs/design-system.md` before editing and include browser or screenshot
verification appropriate to the changed page.
