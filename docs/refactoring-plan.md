# Refactoring Plan

Created: 2026-06-28
Updated: 2026-07-02

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
- Keep production and application-support functions within one screen. Use 30
  lines as the active-code scan threshold outside tests, and allow test methods
  and test helpers up to 60 lines when the scenario remains readable.
- Do not split a test class only because it is long. A long test class is
  acceptable when it has one focused subject, one coherent setup, and related
  scenarios for the same behavior area. Split test classes only when they cover
  different behavior areas, need different setup, or the shared helpers make
  the tests harder to read.
- Keep tests simple. Do not add test inheritance, base classes, or mixins just
  to reduce line counts. Prefer direct setup in the focused test case and
  small helper functions only when they remove real duplication.
- Do not introduce list/dict/set comprehensions during cleanup. Prefer explicit
  loops so filtering, appending, and early exits stay easy to inspect.
- Use Pyrefly as a whole-repo Python type check during cleanup.
- Do not add trivial pass-through functions. Extract helpers only when they
  name a real concept, isolate non-trivial branching, or make repeated behavior
  safer.
- Treat mixins as a smell during cleanup. Do not introduce new mixins to split
  classes; prefer simpler tests, focused concrete classes, helper functions, or
  composition with named helper objects. When touching existing mixins, consider
  replacing them if it reduces complexity without hiding behavior behind
  pass-through methods.
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
- Avoid index-based loops such as `range(len(items))` and slice-window loops
  unless the index itself is the domain value. Prefer `enumerate(...)` for
  position plus item, or an explicit accumulator when building batches.
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

- [x] Split Datamailer email-preference category parsing and payload helpers
  out of the client service module.
- [x] Split cadmin Datamailer operations outbox and send-audit query helpers
  out of the page context module.
- [x] Replace production tuple-return records that inlined meaningful function
  or constructor calls with named local variables.
- [x] Decompose project-create API attribute validation into required-input
  and parsed-date value objects.
- [x] Split cadmin view-model queryset/search construction out of enrollment
  and project-submission list data assembly.
- [x] Simplify deadline reminder payload assembly by passing reminder event
  data directly into key, list, and URL helpers.
- [x] Reuse shared Datamailer score-notification URL helpers for project score
  payloads and keep only project results URL assembly local.
- [x] Split recipient-list sync command option-to-batch construction out of
  the command handler.
- [x] Name Datamailer recipient-list metadata, list-name, and ordering-key
  values before constructing payload/outbox event objects.
- [x] Split account settings, email preference, timezone, and enrollment
  profile tests out of the oversized mixed `accounts/tests.py` module.
- [x] Decompose answer generation in the `add_more_test_data.py` seed script
  so answer selection and persistence are separate steps.
- [x] Flatten seed-script fixture tables so joined answers, random timings,
  deadline deltas, and fixture records are named before construction.
- [x] Flatten initial data-script homework question fixtures so possible-answer
  strings and saved answer records are named before persistence.
- [x] Shorten load-project-data script tests by naming quiet import execution
  and enrollment import fixtures. Verification:
  `uv run ruff check courses/tests/test_load_project_data_script.py` and
  `uv run python manage.py test courses.tests.test_load_project_data_script`.
- [x] Split project statistics view and integration tests out of the
  calculation-focused `courses/tests/test_project_statistics.py` module.
- [x] Shorten project detail/submission view tests by reusing route, POST,
  expected-field, and repeated-copy assertion helpers.
- [x] Split public project detail and submission POST tests into focused
  modules with shared project-view fixtures in a base module.
- [x] Split project scoring test fixtures and project-results option-vote tests
  out of the oversized project score test module.
- [x] Split project score bonus and pass/fail outcome tests into focused
  modules so median scoring tests stay small.
- [x] Shorten project score bonus peer-review tests by naming linked-review
  setup and bonus score assertions. Verification:
  `uv run ruff check courses/tests/test_project_score_bonus.py` and
  `uv run python manage.py test courses.tests.test_project_score_bonus`.
- [x] Remove internal compatibility re-exports for Datamailer templates and
  wrapped statistics, and import Datamailer request data from its owner module.
- [x] Split scored homework result view tests out of the oversized homework
  detail test module.
- [x] Split homework scoring view rendering and warning tests into focused
  modules with shared scoring-view fixtures. Verification:
  `uv run ruff check courses/tests/homework_scoring_view_base.py courses/tests/homework_scoring_view_expectations.py courses/tests/test_homework_scoring_view.py courses/tests/test_homework_scoring_view_warnings.py`
  and
  `uv run python manage.py test courses.tests.test_homework_scoring_view courses.tests.test_homework_scoring_view_warnings`.
- [x] Replace remaining large tuple unpacking in project statistics tests with
  named values or a dataclass.
- [x] Split optional homework submission-field tests out of the oversized
  homework detail test module.
- [x] Shorten homework submission integration tests by naming submitted-answer
  records and reused learning-in-public rejection helpers. Verification:
  `uv run ruff check courses/tests/test_homework_submission_integrations.py`
  and
  `uv run python manage.py test courses.tests.test_homework_submission_integrations`.
- [x] Shorten shared homework detail view question fixtures while preserving
  creation order. Verification:
  `uv run ruff check courses/tests/homework_view_base.py courses/tests/test_homework.py courses/tests/test_homework_submission_view.py`
  and
  `uv run python manage.py test courses.tests.test_homework courses.tests.test_homework_submission_view`.
- [x] Split cadmin homework view test helpers and submission-edit tests out of
  the oversized cadmin homework view test module.
- [x] Split all-project-submissions course page tests out of the oversized
  course detail test module.
- [x] Split project statistics admin-action tests out of the oversized project
  statistics test module.
- [x] Split homework submission validation tests out of the oversized homework
  detail test module.
- [x] Split homework detail and submission POST tests into focused modules with
  shared homework-view fixtures in a base module.
- [x] Split dashboard integration and authentication tests out of the oversized
  dashboard test module.
- [x] Split project-statistics dashboard tests out of the mixed dashboard test
  module so basic/homework and project dashboard behavior are separate.
- [x] Split course duplication admin tests out of the oversized course detail
  test module.
- [x] Split course detail view fixture helpers and certificate-display tests
  out of the oversized course detail test module.
- [x] Shorten the not-enrolled course detail test by moving repeated homework
  state assertions into the shared course-view fixture base. Verification:
  `uv run ruff check courses/tests/test_course.py courses/tests/course_view_base.py`
  and `uv run python manage.py test courses.tests.test_course`.
- [x] Split project list view tests out of the oversized project evaluation
  test module.
- [x] Extract deadline reminder event planning from the management command into
  a focused `courses.deadline_reminder_events` module.
- [x] Split deadline reminder planning helpers by responsibility into type,
  member, query, and event modules.
- [x] Split deadline reminder command tests into common fixtures plus focused
  homework, project-submission, peer-review, and dry-run modules.
- [x] Split API homework list/create serialization helpers out of the oversized
  homework API view module.
- [x] Split API homework upsert validation and save flow out of the public
  homework API view module.
- [x] Split homework API test fixtures, scoring tests, and staff-auth tests
  out of the oversized mixed homework API test module.
- [x] Split API project list/create serialization helpers out of the oversized
  project API view module.
- [x] Split API project upsert validation and save flow out of the public
  project API view module.
- [x] Split project API test fixtures, assign/score action tests, and
  staff-auth tests out of the oversized mixed project API test module.
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
- [x] Split enrollment API tests into graduate export, passed-enrollment
  helper, and certificate-update modules with shared fixtures. Verification:
  `uv run ruff check data/tests/enrollment_base.py data/tests/test_enrollment.py data/tests/test_enrollment_passed.py data/tests/test_enrollment_certificates.py`
  and
  `uv run python manage.py test data.tests.test_enrollment data.tests.test_enrollment_passed data.tests.test_enrollment_certificates`.
- [x] Shorten data endpoint method-restriction tests by naming route groups and
  shared rejected-method assertions. Verification:
  `uv run ruff check data/tests/test_method_restrictions.py` and
  `uv run python manage.py test data.tests.test_method_restrictions`.
- [x] Split the public project detail view into route handling, page-context,
  and submission-edit modules so the view module only coordinates responses.
- [x] Split homework upsert API internals into shared rules, validation,
  question replacement, and persistence modules while keeping the public
  upsert view module as the coordinator.
- [x] Split course homepage display metadata out of the public course list view
  so list and detail pages share it through a direct owner module.
- [x] Split course API serialization and mutation workflows out of the public
  course API view module, keeping list/detail handlers as coordinators.
- [x] Shorten API course detail and staff-token tests by naming detail
  fixtures, payload assertions, non-staff mutation responses, and unchanged
  state assertions. Verification: `uv run ruff check api/tests/test_courses.py`
  and `uv run python manage.py test api.tests.test_courses`.
- [x] Split dashboard metric calculation into common metric, homework,
  project, and context modules, leaving the dashboard view as the route/render
  boundary.
- [x] Split project evaluation submit context decoration and review persistence
  out of the route-level submit view.
- [x] Split project evaluation test helpers and eval-page tests out of the
  mixed project evaluation test module.
- [x] Shorten the project-evaluation submit POST test by naming learning-in-
  public fixture links and saved-link assertions. Verification:
  `uv run ruff check courses/tests/test_project_eval.py` and
  `uv run python manage.py test courses.tests.test_project_eval`.
- [x] Split cached course leaderboard data and score-breakdown query helpers
  out of the leaderboard view module.
- [x] Split course leaderboard tests into shared fixtures plus focused
  leaderboard, score-breakdown, and complaint modules.
- [x] Split registration campaign API serialization, mutation, and
  registration-list helpers out of the public API view module.
- [x] Split cadmin homework submission listing/search and submission edit
  helpers out of the homework admin action module.
- [x] Split cadmin campaign form/edit, metrics, and registration-list helpers
  out of the public campaign route module.
- [x] Split cadmin project submission listing and edit helpers out of the
  project admin action module while preserving notification patch points.
- [x] Split cadmin project view tests into shared fixtures plus focused
  listing, submission-edit, and project-action test modules.
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
- [x] Shorten API question staff-token tests by naming the non-staff client,
  mutation responses, forbidden assertion, and unchanged-state assertion.
  Verification: `uv run ruff check api/tests/test_questions.py` and
  `uv run python manage.py test api.tests.test_questions`.
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
- [x] Split Datamailer recipient-list command test helpers and import-by-
  reference cases out of the oversized recipient-list command test module.
- [x] Split Datamailer membership outbox event builders out of the public
  membership sync entry-point module.
- [x] Split Datamailer webhook request authentication, JSON parsing, and field
  validation out of the route/persistence module.
- [x] Split homework submission POST field application and validation helpers
  out of the submission persistence/callback module.
- [x] Split homework submitted-answer query and display payload helpers out of
  the submitted-content summary module.
- [x] Split homework detail lookup and template-context builders out of the
  route/POST coordinator module.
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
- [x] Split homework POST field preview binding and validation-context
  reconstruction out of the public POST response handler.
- [x] Split project upsert validation, patch rules, and persistence out of the
  public project upsert route module.
- [x] Remove the over-abstracted homework-create loader dataclasses and keep
  the create validation flow explicit and linear.
- [x] Remove the matching over-abstracted project-create dataclasses and
  expand the create validation flow into named local steps.
- [x] Split certificate update validation and notification/persistence side
  effects out of the certificate update apply coordinator.
- [x] Split Datamailer registration confirmation, contact, and recipient-list
  payload builders into direct owner modules and remove the mixed module.
- [x] Split course-list enrollment and registration state decoration out of
  the public course-list context module.
- [x] Split the peer-review assignment selection algorithm out of the project
  assignment state-transition coordinator.
- [x] Split homework submitted-answer formatting helpers out of the homework
  answer processing module.
- [x] Split Datamailer outbox batch-run bookkeeping out of the single-event
  dispatch module.
- [x] Split homework correct-answer maintenance out of the submission scoring
  orchestration module.
- [x] Split project review-score aggregation out of the project submission
  scoring mutation module.
- [x] Split optional project-evaluation add/delete actions out of the project
  evaluation page context module.
- [x] Split Datamailer certificate availability and course-graduate
  recipient-list payload builders into direct owner modules and remove the
  mixed certificate payload module.
- [x] Split public course calendar ICS/event generation out of the route module,
  leaving the view as the HTTP response boundary.
- [x] Split Datamailer recipient-list source querysets and source constants out
  of batch aggregation, with one owner for recipient-list kinds.
- [x] Split Datamailer recipient-list membership removal entry points out of
  the membership upsert/sync module.
- [x] Split homework answer correctness rules out of submission score mutation
  so scoring orchestration no longer owns answer parsing/checking.
- [x] Split public wrapped page lookup/context helpers out of the route module,
  leaving wrapped views as render boundaries.
- [x] Split Datamailer homework and project score notification payload builders
  into direct owner modules and remove the mixed score payload module.
- [x] Split Datamailer score and peer-review notification send flows out of
  the registration-confirmation notification module.
- [x] Split registration user-profile update rules out of the registration form
  module.
- [x] Split public course page data lookup and context builders out of the
  route module.
- [x] Shorten the Datamailer project-score submitter notification test by
  reusing existing project-score submission fixtures and single-member
  assertions. Verification:
  `uv run ruff check courses/tests/test_datamailer_project_scores.py` and
  `uv run python manage.py test courses.tests.test_datamailer_project_scores`.
- [x] Split Datamailer contact write endpoint test cases into named case
  builders so the method-case aggregator stays short and explicit.
  Verification: `uv run ruff check courses/tests/test_datamailer_client.py`
  and `uv run python manage.py test courses.tests.test_datamailer_client`.
- [x] Shorten the cadmin homework-submission search test by moving repeated
  searchable-submission setup into the shared homework cadmin fixture base.
  Verification:
  `uv run ruff check cadmin/tests/test_homework_views.py cadmin/tests/homework_view_base.py`
  and `uv run python manage.py test cadmin.tests.test_homework_views`.
- [x] Split Datamailer peer-review assignment test fixture setup into named
  project, submission, and assignment builders. Verification:
  `uv run ruff check courses/tests/test_datamailer_peer_review.py` and
  `uv run python manage.py test courses.tests.test_datamailer_peer_review`.
- [x] Shorten the Learning in Public score-zeroing test by naming scored
  homework/project submission fixtures and post-disable score assertions.
  Verification:
  `uv run ruff check courses/tests/test_disable_learning_in_public.py` and
  `uv run python manage.py test courses.tests.test_disable_learning_in_public`.
- [x] Split project-evaluation review-criteria fixture setup into named
  code-quality, documentation, and best-practices criteria builders.
  Verification: `uv run ruff check courses/tests/project_eval_base.py`
  and
  `uv run python manage.py test courses.tests.test_project_eval courses.tests.test_project_eval_view`.
- [x] Split project-submission confirmation expected-field records into
  repository and project-detail field groups. Verification:
  `uv run ruff check courses/tests/project_view_base.py` and
  `uv run python manage.py test courses.tests.test_project_submission_view`.
- [x] Shorten the RDS export missing-column test by naming copy-plan,
  target-schema, column-copy-data, and expected-plan assertion helpers.
  Verification:
  `uv run ruff check courses/tests/test_load_rds_export_script.py` and
  `uv run python manage.py test courses.tests.test_load_rds_export_script`.
- [x] Shorten the project-evaluation optional-review view test by naming the
  no-submission setup, volunteer-review fixture, authenticated request, and
  expected page assertions. Verification:
  `uv run ruff check courses/tests/test_project_eval_view.py` and
  `uv run python manage.py test courses.tests.test_project_eval_view`.
- [x] Shorten project optional-review delete tests by reusing shared
  submission/review builders, delete request helper, and review-existence
  assertions. Verification:
  `uv run ruff check courses/tests/test_project_assign.py` and
  `uv run python manage.py test courses.tests.test_project_assign`.
- [x] Shorten project pass/fail outcome scoring tests by naming required
  reverse-review setup, passing-score setup, and final score outcome
  assertions. Verification:
  `uv run ruff check courses/tests/test_project_score_outcomes.py` and
  `uv run python manage.py test courses.tests.test_project_score_outcomes`.
- [x] Shorten registration campaign course-page tests by naming the registered
  user fixture and shared intro-homework fixture. Verification:
  `uv run ruff check courses/tests/test_registration_campaigns.py` and
  `uv run python manage.py test courses.tests.test_registration_campaigns`.
- [x] Shorten dashboard formatted-time display test by naming the quartile
  fixture submissions and formatted-field assertions. Verification:
  `uv run ruff check courses/tests/test_dashboard.py` and
  `uv run python manage.py test courses.tests.test_dashboard`.
- [x] Shorten unauthenticated homework detail submission-field test by naming
  optional-field setup, login-preview assertions, and hidden-field assertions.
  Verification:
  `uv run ruff check courses/tests/test_homework.py courses/tests/homework_view_base.py`
  and `uv run python manage.py test courses.tests.test_homework`.
- [x] Shorten leaderboard completed-project export test by naming the completed
  project fixture, project-submission fixture, response lookup, and exported
  project assertions. Verification:
  `uv run ruff check data/tests/test_leaderboard.py` and
  `uv run python manage.py test data.tests.test_leaderboard`.
- [x] Shorten the e2e homework UI submission test by naming readiness checks,
  question-id resolution, answer mapping, submission payload construction, and
  confirmation assertion. Verification:
  `uv run ruff check e2e/tests/test_03_homework.py` and
  `uv run pytest e2e/tests/test_03_homework.py --collect-only -q`.
- [x] Flatten peer-review assignment pool construction by replacing nested
  `list(range(...))` with an explicit named project-pool builder. Verification:
  `uv run ruff check courses/project_assignment_selection.py` and
  `uv run python manage.py test courses.tests.test_unit_projects courses.tests.test_project_assign`.
- [x] Name the account settings preferred-timezone widget before passing it
  into the `ChoiceField` declaration. Verification:
  `uv run ruff check accounts/forms.py` and
  `uv run python manage.py test accounts.tests_account_settings accounts.tests_timezone`.
- [x] Add OpenAPI schema response/request-body helpers and use them in data
  endpoint path declarations to avoid repeated `response(..., ref(...))` and
  `request_body(ref(...))` nesting. Verification:
  `uv run ruff check api/openapi/primitives.py api/openapi/data_paths.py` and
  `uv run python manage.py test api.tests.test_openapi`.
- [x] Simplify e2e course admin deletion by removing a trivial course-absence
  wrapper and shortening the admin-delete method documentation. Verification:
  `uv run ruff check e2e/browser.py` and
  `uv run pytest e2e/tests/test_07_browser_helpers.py --collect-only -q`.
- [x] Name Datamailer project-score test users, timestamps, list keys, counts,
  and selected member values before helper calls, assertions, or value-object
  construction. Verification:
  `uv run ruff check courses/tests/test_datamailer_project_scores.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_project_scores`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name API question test URLs, JSON request bodies, timestamps, queryset
  existence checks, and count assertions before client calls or assertions.
  Verification: `uv run ruff check api/tests/test_questions.py` and
  `uv run python manage.py test api.tests.test_questions`; touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name API homework test URLs, JSON request bodies, ordered querysets, and
  queryset existence checks before client calls, list conversion, or assertions.
  Verification: `uv run ruff check api/tests/test_homeworks.py` and
  `uv run python manage.py test api.tests.test_homeworks`; touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name API project test URLs, JSON request bodies, invalid-state payloads,
  and queryset existence checks before client calls or assertions.
  Verification: `uv run ruff check api/tests/test_projects.py` and
  `uv run python manage.py test api.tests.test_projects`; touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name API course test date values, JSON request bodies, and queryset
  existence checks before model creation, client calls, or assertions.
  Verification: `uv run ruff check api/tests/test_courses.py` and
  `uv run python manage.py test api.tests.test_courses`; touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name project-submission view test counts, selected submissions, and POST
  data before assertions or request helper calls. Verification:
  `uv run ruff check courses/tests/test_project_submission_view.py` and
  `uv run python manage.py test courses.tests.test_project_submission_view`;
  touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name registration-campaign test URLs, payloads, due dates, and registration
  counts before client calls, model creation, or assertions. Verification:
  `uv run ruff check courses/tests/test_registration_campaigns.py` and
  `uv run python manage.py test courses.tests.test_registration_campaigns`;
  touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name project-assignment test deadlines, peer-review querysets, URLs,
  counts, existence checks, and redirect targets before model creation, request
  calls, list conversion, or assertions. Verification:
  `uv run ruff check courses/tests/test_project_assign.py` and
  `uv run python manage.py test courses.tests.test_project_assign`; touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name homework view test-base URLs, enrollment/submission existence checks,
  and expected option records before request helpers, redirects, or assertions.
  Verification:
  `uv run ruff check courses/tests/homework_view_base.py courses/tests/test_homework.py courses/tests/test_homework_submission_view.py`
  and
  `uv run python manage.py test courses.tests.test_homework courses.tests.test_homework_submission_view`;
  touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name homework-submissions view test due dates, request URLs, redirect
  targets, and expected admin links before model creation, request helpers, or
  assertions. Verification:
  `uv run ruff check courses/tests/test_homework_submissions.py` and
  `uv run python manage.py test courses.tests.test_homework_submissions`;
  touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name create-superuser script project-root and email queryset values before
  path insertion or list conversion. Verification:
  `uv run ruff check scripts/create_superuser.py`,
  `uv run python scripts/create_superuser.py --help`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name score-project script project-root and submission-count values before
  path insertion or output formatting. Verification:
  `uv run ruff check scripts/score_project.py`,
  `uv run python scripts/score_project.py --help`, and touched-file nested-call
  scans report `touched_file_nested_calls=0`.
- [x] Name move-criteria script project-root and ordered criteria queryset
  values before path insertion or list conversion. Verification:
  `uv run ruff check scripts/move_criteria.py`,
  `uv run python scripts/move_criteria.py --help`, and touched-file nested-call
  scans report `touched_file_nested_calls=0`.
- [x] Name debug-score-project script project-root and submission-items values
  before path insertion or enumerating submission dictionaries. Verification:
  `uv run ruff check scripts/debug_score_project.py`,
  `uv run python scripts/debug_score_project.py --help`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name analyze-scoring-bug script project-root and queryset count values
  before path insertion or output formatting. Verification:
  `uv run ruff check scripts/analyze_scoring_bug.py`,
  `uv run python -c "from scripts.analyze_scoring_bug import parse_args; print(parse_args(['analyze_scoring_bug.py', 'course', 'project']))"`,
  and touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name score-project-dev script project-root, `.envrc` path, and
  submission-count values before path insertion, file opening, or output
  formatting. Verification: `uv run ruff check scripts/score_project_dev.py`,
  `python -m py_compile scripts/score_project_dev.py`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name homework, project, and peer-review state choice lists before passing
  them into model field declarations. Verification:
  `uv run ruff check courses/models/project.py courses/models/homework.py`,
  `uv run python manage.py makemigrations --check --dry-run`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name e2e conftest API-token and timestamp values before client
  construction or namespace generation. Verification:
  `uv run ruff check e2e/conftest.py`, `python -m py_compile e2e/conftest.py`,
  and touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name e2e API error bodies, namespace timestamps, and email-match
  criteria before error construction, namespace generation, or wait-request
  construction. Verification:
  `uv run ruff check e2e/api_client.py e2e/provisioning.py e2e/tests/test_03_homework.py e2e/tests/test_04_project.py`,
  `python -m py_compile e2e/api_client.py e2e/provisioning.py e2e/tests/test_03_homework.py e2e/tests/test_04_project.py`,
  and touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name mock-inbox test dotenv contents and wait-message criteria before
  file writes or wait-request construction. Verification:
  `uv run ruff check e2e/tests/test_06_mock_inbox_client.py`,
  `python -m py_compile e2e/tests/test_06_mock_inbox_client.py`,
  `uv run pytest e2e/tests/test_06_mock_inbox_client.py -q`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name production-like leaderboard generator homework and project slugs
  before `update_or_create` calls. Verification:
  `uv run ruff check scripts/generate_production_like_leaderboard_data.py`,
  `python -m py_compile scripts/generate_production_like_leaderboard_data.py`,
  and touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name e2e browser helper URLs, selector/count values, link limits, and
  login redirect patterns before Playwright calls. Verification:
  `uv run ruff check e2e/browser.py`, `python -m py_compile e2e/browser.py`,
  `uv run pytest e2e/tests/test_07_browser_helpers.py -q`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name RDS export loader env defaults, table-model lookup, insert SQL,
  SQLite sequence max id, and process exit code before parser, copy, sequence,
  or exit calls. Verification:
  `uv run ruff check scripts/load_rds_export.py`,
  `python -m py_compile scripts/load_rds_export.py`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name project-data pull script path setup, queryset ID lists, and extracted
  JSONL records before path insertion, filters, or write calls. Verification:
  `uv run ruff check scripts/pull_project_data.py`,
  `python -m py_compile scripts/pull_project_data.py`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name small OpenAPI schema refs, array schemas, and auth-error response
  values before schema or response construction. Verification:
  `uv run ruff check api/openapi/primitives.py api/openapi/course_schemas.py api/openapi/integration_schemas.py api/openapi/content_schemas/homeworks.py api/openapi/content_schemas/projects.py api/openapi/content_schemas/questions.py`,
  `python -m py_compile api/openapi/primitives.py api/openapi/course_schemas.py api/openapi/integration_schemas.py api/openapi/content_schemas/homeworks.py api/openapi/content_schemas/projects.py api/openapi/content_schemas/questions.py`,
  and touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name OpenAPI data-route response maps, content schemas, request bodies,
  operation data, and operation records before path registry construction.
  Verification: `uv run ruff check api/openapi/data_paths.py`,
  `python -m py_compile api/openapi/data_paths.py`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name OpenAPI course-route refs, response maps, request bodies, operation
  data, and operation records before path registry construction.
  Verification: `uv run ruff check api/openapi/course_paths.py`,
  `python -m py_compile api/openapi/course_paths.py`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Name project-data loader path setup, parsed records, defaults, model
  kwargs, mapped ids, and optional submission/review fields before path,
  parser, queryset, or model construction calls, and remove a trivial batch
  flush pass-through helper. Verification:
  `uv run ruff check scripts/load_project_data.py`,
  `python -m py_compile scripts/load_project_data.py`, touched-file
  nested-call scans report `touched_file_nested_calls=0`, and function-length
  scans report no function over 30 lines.
- [x] Name OpenAPI question-route refs, response maps, request bodies,
  operation data, and operation records before path registry construction.
  Verification: `uv run ruff check api/openapi/content_paths/questions.py`,
  `python -m py_compile api/openapi/content_paths/questions.py`, and
  touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name OpenAPI homework-route refs, shared response maps, request bodies,
  descriptions, operation data, and operation records before path registry
  construction. Verification:
  `uv run ruff check api/openapi/content_paths/homeworks.py`,
  `python -m py_compile api/openapi/content_paths/homeworks.py`, and
  touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Name OpenAPI project-route refs, shared response maps, request bodies,
  descriptions, operation data, and operation records before path registry
  construction. Verification:
  `uv run ruff check api/openapi/content_paths/projects.py`,
  `python -m py_compile api/openapi/content_paths/projects.py`, and
  touched-file nested-call scans report `touched_file_nested_calls=0`.
- [x] Remove the single-use homework-by-slug query helper and keep the lookup
  explicit in the upsert coordinator with a named queryset. Verification:
  `uv run ruff check api/views/homework_upsert.py api/views/homework_upsert_save.py`,
  `python -m py_compile api/views/homework_upsert.py api/views/homework_upsert_save.py`,
  `uv run python manage.py test api.tests.test_homeworks`, and touched-file
  nested-call scans report `touched_file_nested_calls=0`.
- [x] Remove the single-use debug-score submission-data constructor helper and
  construct `SubmissionDebugData` directly from named context values.
  Verification: `uv run ruff check scripts/debug_score_project.py`,
  `python -m py_compile scripts/debug_score_project.py`, touched-file
  nested-call scans report `touched_file_nested_calls=0`, and function-length
  scans report no function over 30 lines.
- [x] Replace the invalid project-submission preservation helper's multi-value
  argument list with a named expectation object. Verification:
  `uv run ruff check courses/tests/test_project_submission_view.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_submission_view`,
  touched-file helper scans report no five-argument helpers, and repo cleanup
  gates still allow tests up to 60 lines.

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
uv run python manage.py test \
  courses.tests.test_deadline_reminder_homework \
  courses.tests.test_deadline_reminder_project \
  courses.tests.test_deadline_reminder_peer_review \
  courses.tests.test_deadline_reminder_dry_run
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
uv run python manage.py test \
  courses.tests.test_deadline_reminder_homework \
  courses.tests.test_deadline_reminder_project \
  courses.tests.test_deadline_reminder_peer_review \
  courses.tests.test_deadline_reminder_dry_run
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
- [x] Shorten Datamailer status command tests by naming the command payload,
  runner, and output assertions. Verification:
  `uv run ruff check courses/tests/test_datamailer_status.py` and
  `uv run python manage.py test courses.tests.test_datamailer_status`.
- [x] Split Datamailer contact and transactional-send tests out of the oversized
  Datamailer test module.
- [x] Move Datamailer contact backfill command tests into the contact test
  module.
- [x] Split Datamailer recipient-list backfill, audit, and import command tests
  out of the oversized Datamailer test module.
- [x] Shorten Datamailer recipient-list command tests by naming command
  execution, project-passed reconcile assertions, and dry-run registration
  fixtures. Verification:
  `uv run ruff check courses/tests/test_datamailer_recipient_lists.py` and
  `uv run python manage.py test courses.tests.test_datamailer_recipient_lists`.
- [x] Shorten Datamailer recipient-list import timeout tests by naming
  processing-job setup and timeout assertion flow. Verification:
  `uv run ruff check courses/tests/test_datamailer_recipient_list_imports.py`
  and
  `uv run python manage.py test courses.tests.test_datamailer_recipient_list_imports`.
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
- [x] Shorten Datamailer certificate availability assertions by separating
  identity, context, metadata, and copy checks. Verification:
  `uv run ruff check courses/tests/test_datamailer_certificates.py` and
  `uv run python manage.py test courses.tests.test_datamailer_certificates`.
- [x] Split Datamailer peer-review assignment tests out of the oversized
  Datamailer workflow test module.
- [x] Split Datamailer homework-score publication tests out of the oversized
  Datamailer workflow test module.
- [x] Shorten Datamailer homework-score payload tests by naming scored
  submission setup, payload expectations, and context URL assertions.
  Verification:
  `uv run ruff check courses/tests/test_datamailer_homework_scores.py` and
  `uv run python manage.py test courses.tests.test_datamailer_homework_scores`.
- [x] Rename the remaining Datamailer workflow score tests to a project-score
  test module.
- [x] Split course leaderboard and score-breakdown tests out of the oversized
  course detail test module.
- [x] Split homework scoring workflow, leaderboard update, and correct-answer
  backfill tests out of the oversized scoring test module. Verification:
  `uv run ruff check courses/tests/scoring_base.py courses/tests/test_scoring.py courses/tests/test_scoring_leaderboard.py courses/tests/test_homework_correct_answers.py`
  and
  `uv run python manage.py test courses.tests.test_scoring courses.tests.test_scoring_leaderboard courses.tests.test_homework_correct_answers`.
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
- [x] Shorten the RDS export loader script by splitting admin CLI option
  groups, source-column discovery, table-copy setup, and source-table copy
  iteration into named helpers. Verification:
  `uv run ruff check scripts/load_rds_export.py`,
  `uv run python manage.py test courses.tests.test_load_rds_export_script`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten production-like leaderboard data generation by replacing
  three-value course/enrollment returns with named result objects, naming
  derived homework/project submission values before ORM construction, and
  splitting generated submission persistence from course seeding.
  Verification:
  `uv run ruff check scripts/generate_production_like_leaderboard_data.py`,
  `uv run python scripts/generate_production_like_leaderboard_data.py --list-courses > .tmp/generated_leaderboard_list_courses.txt`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten project-score debug submission processing by moving per-item
  processing, progress reporting, and submission debug-data construction out of
  the top-level loop. Verification:
  `uv run ruff check scripts/debug_score_project.py`,
  `uv run python scripts/debug_score_project.py --help > .tmp/debug_score_project_help.txt`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten public leaderboard data endpoint tests by extracting
  leaderboard-specific fixture creation and scored-homework export assertions
  from the longest setup and assertion methods. Verification:
  `uv run ruff check data/tests/test_leaderboard.py`,
  `uv run python manage.py test data.tests.test_leaderboard`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten course API mutation tests by naming create/patch request
  payloads, JSON request bodies, response assertions, and persisted-state
  assertions. Verification:
  `uv run ruff check api/tests/test_courses.py`,
  `uv run python manage.py test api.tests.test_courses`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten cadmin leaderboard complaint tests by extracting complaint
  enrollment fixtures, complaint creation, and complaint URL builders from the
  longest sorting and resolution scenarios. Verification:
  `uv run ruff check cadmin/tests/test_leaderboard_views.py`,
  `uv run python manage.py test cadmin.tests.test_leaderboard_views`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten project voting limit tests by naming the extra submission
  fixtures used by the three-vote cap scenario. Verification:
  `uv run ruff check courses/tests/test_project_voting.py`,
  `uv run python manage.py test courses.tests.test_project_voting`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten project submission view tests by extracting confirmation-email
  posting/assertions and invalid-link preservation fixtures/assertions from the
  two longest scenarios. Verification:
  `uv run ruff check courses/tests/test_project_submission_view.py`,
  `uv run python manage.py test courses.tests.test_project_submission_view`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten project eval-submit tests by extracting accepting/closed context
  assertions, closed-form copy checks, and the project-review close operation
  from the longest GET scenarios. Verification:
  `uv run ruff check courses/tests/test_project_eval.py`,
  `uv run python manage.py test courses.tests.test_project_eval`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten project statistics tests by extracting course/project/student
  setup, basic raw-stat expectations, and null-time-spent scenario assertions.
  Verification:
  `uv run ruff check courses/tests/test_project_statistics.py`,
  `uv run python manage.py test courses.tests.test_project_statistics`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten Datamailer status tests by naming preference response/update
  payloads, student-user creation, and message-status command output
  assertions. Verification:
  `uv run ruff check courses/tests/test_datamailer_status.py`,
  `uv run python manage.py test courses.tests.test_datamailer_status`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten Datamailer recipient-list import command tests by extracting the
  enrollment import-by-reference command runner and failed import payload.
  Verification:
  `uv run ruff check courses/tests/test_datamailer_recipient_list_imports.py`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_list_imports`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten shared project score test helpers by splitting peer-review
  fixture creation, score-project completion assertions, evaluation-score
  assertions, and submission-score assertions. Verification:
  `uv run ruff check courses/tests/project_score_base.py courses/tests/test_project_score.py courses/tests/test_project_score_outcomes.py courses/tests/test_project_score_bonus.py courses/tests/test_project_results.py`,
  `uv run python manage.py test courses.tests.test_project_score courses.tests.test_project_score_outcomes courses.tests.test_project_score_bonus courses.tests.test_project_results`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten leaderboard view tests by extracting paginated leaderboard
  fixture creation, page assertions, current-student target setup, and the
  shared leaderboard URL helper. Verification:
  `uv run ruff check courses/tests/test_leaderboard.py`,
  `uv run python manage.py test courses.tests.test_leaderboard`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten dashboard homework-stat tests by extracting course, homework,
  statistic-user, and enrollment setup out of the long fixture setup method.
  Verification:
  `uv run ruff check courses/tests/test_dashboard.py`,
  `uv run python manage.py test courses.tests.test_dashboard`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten homework submission integration tests by naming expected
  confirmation submission fields, minimal Datamailer post data, and the saved
  submission assertion. Verification:
  `uv run ruff check courses/tests/test_homework_submission_integrations.py`,
  `uv run python manage.py test courses.tests.test_homework_submission_integrations`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten Datamailer client endpoint tests by splitting contact read,
  recipient-list import, transactional send, and campaign upsert method cases
  into named payload/expectation helpers. Verification:
  `uv run ruff check courses/tests/test_datamailer_client.py`,
  `uv run python manage.py test courses.tests.test_datamailer_client`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten homework deadline reminder helpers by replacing positional
  user/enrollment tuples with named dataclasses and splitting reminder list,
  member, and idempotency assertions. Verification:
  `uv run ruff check courses/tests/deadline_reminder_homework.py courses/tests/test_deadline_reminder_homework.py courses/tests/deadline_reminder_base.py`,
  `uv run python manage.py test courses.tests.test_deadline_reminder_homework`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide comprehension scan, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Shorten optional project-evaluation add/self-eval tests by reusing the
  shared own-submission builder, naming the add-review redirect assertion, and
  moving optional-review existence checks into focused assertions.
  Verification:
  `uv run ruff check courses/tests/test_project_assign.py`,
  `uv run python manage.py test courses.tests.test_project_assign`,
  touched-file style scans for comprehensions/generators, wide loop unpacking,
  and 30+ line functions, repo-wide active-code scans excluding `.tmp` and
  generated migrations (`forbidden_comprehensions=0`,
  `long_functions=32`), `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten project-assignment unit tests by naming the fixture-plus-action
  assignment selector and total-count assertion, while removing the one-line
  reviewer-count assertion helper. Verification:
  `uv run ruff check courses/tests/test_unit_projects.py`,
  `uv run python manage.py test courses.tests.test_unit_projects`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, repo-wide active-code scans excluding `.tmp` and generated
  migrations (`forbidden_comprehensions=0`, `long_functions=31`),
  `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten homework scoring workflow tests by naming submission-with-answer
  setup, OK scoring, and refreshed-submission checks. Verification:
  `uv run ruff check courses/tests/test_scoring.py`,
  `uv run python manage.py test courses.tests.test_scoring`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, repo-wide active-code scans excluding `.tmp` and generated
  migrations (`forbidden_comprehensions=0`, `long_functions=30`),
  `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten Datamailer homework score list-send assertions by splitting the
  result count, client-call, send-audit, and outbox-event checks into named
  assertion helpers. Verification:
  `uv run ruff check courses/tests/test_datamailer_homework_scores.py`,
  `uv run python manage.py test courses.tests.test_datamailer_homework_scores`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, repo-wide active-code scans excluding `.tmp` and generated
  migrations (`forbidden_comprehensions=0`, `long_functions=29`),
  `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten cadmin campaign-create view tests by naming the create payload,
  create-page assertions, and saved-campaign assertions. Verification:
  `uv run ruff check cadmin/tests/test_campaign_views.py`,
  `uv run python manage.py test cadmin.tests.test_campaign_views`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, repo-wide active-code scans excluding `.tmp` and generated
  migrations (`forbidden_comprehensions=0`, `long_functions=28`),
  `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten API question delete-with-answers tests by naming the answered
  question fixture, blocked-delete response assertion, and persistence
  assertion. Verification:
  `uv run ruff check api/tests/test_questions.py`,
  `uv run python manage.py test api.tests.test_questions`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, repo-wide active-code scans excluding `.tmp` and generated
  migrations (`forbidden_comprehensions=0`, `long_functions=27`),
  `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten API homework PUT-by-slug question replacement tests by naming the
  old-question fixture, replacement payload, JSON body, and persisted-question
  assertions. Verification:
  `uv run ruff check api/tests/test_homeworks.py`,
  `uv run python manage.py test api.tests.test_homeworks`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, repo-wide active-code scans excluding `.tmp` and generated
  migrations (`forbidden_comprehensions=0`, `long_functions=26`),
  `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten project statistics integration helpers by naming the incomplete
  project fixture and absent-link assertion, and compacting repeated workflow
  score-row fixture data without adding parameter-heavy helpers. Verification:
  `uv run ruff check courses/tests/test_project_statistics_integration.py`,
  `uv run python manage.py test courses.tests.test_project_statistics_integration`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, repo-wide active-code scans excluding `.tmp` and generated
  migrations (`forbidden_comprehensions=0`, `long_functions=24`),
  `uvx pyrefly check`, and `git diff --check`.
- [x] Shorten homework submissions view tests by naming hidden-answer fixture
  setup, the authenticated submissions request, and compact-list content
  assertions. Verification:
  `uv run ruff check courses/tests/test_homework_submissions.py`,
  `uv run python manage.py test courses.tests.test_homework_submissions`,
  touched-file style scans for comprehensions/generators and 30+ line
  functions, repo-wide active-code scans excluding `.tmp` and generated
  migrations (`forbidden_comprehensions=0`, `long_functions=23`),
  `uvx pyrefly check`, and `git diff --check`.
- [x] Update function-size scanning rules to use a 30-line threshold for
  production/application-support code and a 60-line threshold for tests.
  Verification: repo-wide active-code scan excluding `.tmp` and generated
  migrations reports `threshold_violations=0`; repo-wide comprehension scan
  reports `forbidden_comprehensions=0`.
- [x] Replace remaining inline constructed `append(...)` calls in active code
  by naming the method result before appending. Verification:
  `uv run ruff check courses/tests/test_datamailer_client.py courses/tests/test_homework_submission_integrations.py`,
  `uv run python manage.py test courses.tests.test_datamailer_client courses.tests.test_homework_submission_integrations`,
  repo-wide active-code scan excluding `.tmp` and generated migrations reports
  `append_constructed=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Remove obvious one-off aliases immediately before loops when the iterable
  expression is already clear, such as preference-category values and stored
  form question/criteria lists. Verification:
  `uv run ruff check accounts/forms.py cadmin/forms.py course_management/datamailer/preference_categories.py`,
  `uv run python manage.py test accounts.tests_account_settings accounts.tests_email_preferences accounts.tests_timezone`,
  `uv run python manage.py test cadmin.tests.test_homework_submission_edit_views cadmin.tests.test_project_submission_edit_views`,
  size-threshold scan reports `threshold_violations=0`, comprehension scan
  reports `forbidden_comprehensions=0`, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name the Datamailer outbox run failure error before finalizing a failed
  run, and split successful/failed run finalization into outcome-specific
  helpers so the main workflow stays below the production threshold.
  Verification:
  `uv run ruff check course_management/datamailer_outbox_runs.py`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox`,
  touched-file nested-call scan reports `touched_file_nested_call_arguments=0`,
  size-threshold scan reports `threshold_violations=0`, comprehension scan
  reports `forbidden_comprehensions=0`, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name meaningful intermediates in the deadline reminder command and split
  successful/failed reminder-send audit recording into outcome-specific
  helpers. Verification:
  `uv run ruff check courses/management/commands/send_deadline_reminders.py`,
  `uv run python manage.py test courses.tests.test_deadline_reminder_homework courses.tests.test_deadline_reminder_project courses.tests.test_deadline_reminder_peer_review courses.tests.test_deadline_reminder_dry_run`,
  touched-file nested-call scan reports `touched_file_nested_call_arguments=0`,
  size-threshold scan reports `threshold_violations=0`, comprehension scan
  reports `forbidden_comprehensions=0`, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Replace the Datamailer contact backfill slice-window batching loop with
  explicit batch accumulation so the helper no longer depends on
  `range(len(...))`-style indexing. Verification:
  `uv run ruff check courses/management/commands/sync_datamailer_contacts.py`,
  `uv run python manage.py test courses.tests.test_datamailer_contact`,
  touched-file nested-call scan reports `touched_file_nested_call_arguments=0`,
  size-threshold scan reports `threshold_violations=0`, comprehension scan
  reports `forbidden_comprehensions=0`, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Replace remaining three-value tuple unpacking in active Python files by
  naming dotenv parsing steps and using request-call/result dataclasses in e2e
  support tests and the dev scoring script. Verification:
  `uv run ruff check e2e/config.py e2e/tests/test_06_mock_inbox_client.py e2e/tests/test_07_api_client.py scripts/score_project_dev.py`,
  `uv run pytest e2e/tests/test_06_mock_inbox_client.py e2e/tests/test_07_api_client.py`,
  wide tuple-unpacking scan reports `wide_tuple_unpacking=0`,
  size-threshold scan reports `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name e2e settings environment values before constructing the `Settings`
  object and move timeout parsing into explicit typed helpers. Verification:
  `uv run ruff check e2e/config.py docs/refactoring-plan.md`,
  `uv run pytest e2e/tests/test_06_mock_inbox_client.py`,
  touched-file nested-call scan reports `touched_file_nested_call_arguments=0`,
  size-threshold scan reports `threshold_violations=0`, comprehension scan
  reports `forbidden_comprehensions=0`, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Flatten e2e inbox message parsing so mock and real inbox summaries name
  response fields before populating `InboxMessage`, and metadata dictionaries
  no longer inline `item.get(...)` calls. Verification:
  `uv run ruff check e2e/mock_inbox.py docs/refactoring-plan.md`,
  `uv run pytest e2e/tests/test_06_mock_inbox_client.py`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_inline_dict_calls=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name deadline ISO strings before constructing deadline reminder context
  dictionaries in homework, project-submission, peer-review, and shared
  reminder payload helpers. Verification:
  `uv run ruff check courses/deadline_reminder_items.py courses/deadline_reminder_payloads.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_deadline_reminder_homework courses.tests.test_deadline_reminder_project courses.tests.test_deadline_reminder_peer_review courses.tests.test_deadline_reminder_dry_run`,
  touched-file inline dictionary-call scan reports
  `touched_file_inline_dict_calls=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer peer-review assignment context fragments and deadline
  ISO strings before merging payload context dictionaries. Verification:
  `uv run ruff check course_management/datamailer/payloads/peer_review.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_peer_review`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name project-submission recipient-list metadata fragments before merging
  identity, score, source, and status metadata dictionaries. Verification:
  `uv run ruff check course_management/datamailer/payloads/submissions.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_project_scores`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name shared Datamailer contact and recipient-list member payload values
  before constructing payload dictionaries, including platform user IDs,
  course-family slugs, normalized member emails, and source metadata.
  Verification:
  `uv run ruff check course_management/datamailer/payloads/base.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_contact courses.tests.test_datamailer_membership`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer peer-review assigned-review counts before constructing
  recipient metadata dictionaries. Verification:
  `uv run ruff check course_management/datamailer/payloads/peer_review_members.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_peer_review`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer outbox status counts and lookup results before returning
  the status summary dictionary. Verification:
  `uv run ruff check course_management/datamailer_outbox_status.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name API course serializer date strings before constructing course,
  homework, and project response dictionaries. Verification:
  `uv run ruff check api/views/course_serializers.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_courses`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name API homework and project serializer counts and deadline strings
  before constructing response dictionaries, with project deadline fields
  grouped in a focused helper. Verification:
  `uv run ruff check api/views/homework_serializers.py api/views/project_serializers.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_homeworks api.tests.test_projects`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name cadmin Datamailer outbox event counts before constructing status
  rows for the operations page. Verification:
  `uv run ruff check cadmin/views/datamailer_outbox_operations.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_datamailer_views`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer outbox dispatch error and response string values before
  updating status dictionaries or returning response payload dictionaries.
  Verification:
  `uv run ruff check course_management/datamailer_outbox_dispatch.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name API registration, homework-create, project-action, and
  course-create values before constructing response or model dictionaries.
  Verification:
  `uv run ruff check api/views/registration_campaign_serializers.py api/views/homework_create.py api/views/project_actions.py api/views/course_mutations.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_registration_campaigns api.tests.test_homeworks api.tests.test_project_actions api.tests.test_project_scoring api.tests.test_courses`,
  touched-file scans report `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and
  `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Replace long wrapped-statistics constructor calls with named value
  mappings before creating metric and user-stat objects. Verification:
  `uv run ruff check courses/wrapped_statistics/metrics.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_wrapped_statistics courses.tests.test_wrapped_views`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Group project submission viewer state in a dataclass and pass it through
  listing decoration as one concept instead of unpacking it into a long
  constructor call. Verification:
  `uv run ruff check courses/views/project_submission_display.py courses/views/project_submission_listing.py courses/views/project_submission_viewer.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_submission_view courses.tests.test_project_voting courses.tests.test_project_view courses.tests.test_project_list_view`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Move Datamailer project passed-outcome sync data assembly behind a
  focused helper so the score-send path no longer unpacks eight constructor
  fields at the call site. Verification:
  `uv run ruff check course_management/datamailer/sync/score_notifications.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_project_scores`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Group project upsert create fields in `ProjectUpsertCreateData` and build
  the model from named values instead of an eight-field manager call.
  Verification:
  `uv run ruff check api/views/project_upsert_persistence.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_projects`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Replace deadline reminder spec factory functions with named static spec
  values and constants so reminder event planning no longer uses trivial
  pass-through factories or nine-field constructor calls. Verification:
  `uv run ruff check courses/deadline_reminder_specs.py courses/deadline_reminder_events.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_deadline_reminder_homework courses.tests.test_deadline_reminder_project courses.tests.test_deadline_reminder_peer_review courses.tests.test_deadline_reminder_dry_run`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, production high-argument scan reports
  `total=0`, size-threshold scan reports `threshold_violations=0`,
  comprehension scan reports `forbidden_comprehensions=0`, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Name student-facing registration, enrollment, and complaint form widgets
  before form field and widget-map construction, preserving existing classes
  from the design-system form layout. Verification:
  `uv run ruff check courses/views/registration_form.py courses/views/forms.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_registration_campaigns courses.tests.test_certificate_name courses.tests.test_course_leaderboard_complaints`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name Cadmin registration campaign form widgets before the widget map,
  preserving existing dense operational form classes. Verification:
  `uv run ruff check cadmin/forms.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_campaign_views`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name Django admin question and review-criteria widgets before admin form
  widget-map construction. Verification:
  `uv run ruff check courses/admin/homework.py courses/admin/course.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_admin_criteria_form courses.tests.test_course_duplication courses.tests.test_homework_correct_answers`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Name settings env conversion inputs and translated Unfold labels before
  settings dictionary construction. Verification:
  `uv run ruff check course_management/settings.py docs/refactoring-plan.md`,
  `uv run python manage.py check`, touched-file scans report
  `touched_file_high_arg_calls=0`, `touched_file_inline_dict_calls=0`,
  `touched_file_nested_call_arguments=0`, and `touched_file_long_functions=0`,
  inline-construction scan reports `total_calls=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Remove the trivial `wrapped_project_hours` pass-through helper and name
  project submission time at the total-hours calculation site. Verification:
  `uv run ruff check courses/wrapped_statistics/metrics.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_wrapped_statistics courses.tests.test_wrapped_views`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Remove the trivial homework POST preview value pass-through helper and
  name each preserved POST value where it is applied. Verification:
  `uv run ruff check courses/views/homework_post_fields.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_optional_fields courses.tests.test_homework_submission_integrations`,
  touched-file scans report `touched_file_high_arg_calls=0`,
  `touched_file_inline_dict_calls=0`, `touched_file_nested_call_arguments=0`,
  and `touched_file_long_functions=0`, size-threshold scan reports
  `threshold_violations=0`, comprehension scan reports
  `forbidden_comprehensions=0`, `uvx pyrefly check`, and `git diff --check`.
- [x] Remove one-off loop aliases from project scoring code where the iterable
  expression is already the clearest name. Verification:
  `uv run ruff check courses/project_review_scores.py courses/models/project.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_score courses.tests.test_project_score_outcomes courses.tests.test_project_score_bonus courses.tests.test_project_results`,
  size-threshold scan reports `threshold_violations=0`, comprehension scan
  reports `forbidden_comprehensions=0`, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Remove the remaining project review response loop alias where the loop can
  read directly from the review object. Verification:
  `uv run ruff check courses/project_review_scores.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_score courses.tests.test_project_score_outcomes courses.tests.test_project_score_bonus courses.tests.test_project_results`,
  production loop-alias scan reports `production_loop_aliases=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Remove the two-field homework answer class-state dataclass that only
  forwarded two booleans to one helper. Verification:
  `uv run ruff check courses/views/homework_answers.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework courses.tests.test_homework_scoring_view courses.tests.test_homework_scoring_view_warnings`,
  dataclass small-wrapper scan reviewed, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Replace the two-field registration profile-value dataclass with explicit
  two-item field/value records, which are allowed by the style guide.
  Verification:
  `uv run ruff check courses/views/registration_profile.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_registration_campaigns`,
  dataclass small-wrapper scan reviewed, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Remove the two-field cadmin homework submission questions wrapper and
  unpack the two returned values directly. Verification:
  `uv run ruff check cadmin/views/homework_submission_edit.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_homework_submission_edit_views cadmin.tests.test_homework_views`,
  dataclass small-wrapper scan reviewed, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Remove the one-use project submission viewer-state wrapper and pass the
  submission plus decoration context directly. Verification:
  `uv run ruff check courses/views/project_submission_display.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_submissions_view courses.tests.test_project_voting courses.tests.test_project_view`,
  dataclass small-wrapper scan reviewed, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name URLs, request payloads, and JSON response bodies in account email
  preference tests instead of nesting `reverse(...)` or `response.json()` calls.
  Verification:
  `uv run ruff check accounts/tests_email_preferences.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_email_preferences`,
  nested-call scan reviewed, `uvx pyrefly check`, and `git diff --check`.
- [x] Name URLs, request payloads, and JSON response bodies in account toggle
  tests instead of nesting `reverse(...)` or `response.json()` calls.
  Verification:
  `uv run ruff check accounts/tests_toggles.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_toggles`, touched-file
  nested-call scan reports `touched_file_nested_calls=0`, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Name the timezone preference update URL in the account timezone tests
  instead of nesting `reverse(...)` inside the client call. Verification:
  `uv run ruff check accounts/tests_timezone.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_timezone`, touched-file
  nested-call scan reports `touched_file_nested_calls=0`, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Name token-existence checks before assertions in account token-admin tests
  instead of nesting queryset checks inside `assertFalse(...)`. Verification:
  `uv run ruff check accounts/tests_token_admin.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_token_admin`, touched-file
  nested-call scan reports `touched_file_nested_calls=0`, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Name social email fixtures in account auth tests before building the
  social-login object. Verification:
  `uv run ruff check accounts/tests_auth.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_auth`, touched-file nested-call
  scan reports `touched_file_nested_calls=0`, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name URLs, redirect prefixes, and inline payloads in account settings
  tests instead of nesting `reverse(...)` or constructed values inside calls.
  Verification:
  `uv run ruff check accounts/tests_account_settings.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_account_settings`, touched-file
  nested-call scan reports `touched_file_nested_calls=0`, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Name URLs, inline payloads, form values, and response bodies in account
  enrollment-profile tests instead of nesting route, value, or JSON calls.
  Verification:
  `uv run ruff check accounts/tests_enrollment_profile.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_enrollment_profile`, touched-file
  nested-call scan reports `touched_file_nested_calls=0`, `uvx pyrefly check`,
  and `git diff --check`.
- [x] Name the homework due date in submission timestamp tests instead of
  nesting `timezone.now()` inside model construction. Verification:
  `uv run ruff check courses/tests/test_submission_timestamps.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_submission_timestamps`,
  touched-file nested-call scan reports `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name the enrollment form validity check in certificate-name tests instead
  of nesting `form.is_valid()` inside `assertTrue(...)`. Verification:
  `uv run ruff check courses/tests/test_certificate_name.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_certificate_name`,
  touched-file nested-call scan reports `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name single nested values in small API, cadmin, course-helper, and data
  test modules instead of nesting route/helper/query calls directly in client
  calls or assertions. Verification:
  `uv run ruff check api/tests/test_homework_scoring.py cadmin/tests/test_campaign_views.py courses/tests/test_registration_helpers.py data/tests/test_enrollment.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_homework_scoring cadmin.tests.test_campaign_views courses.tests.test_registration_helpers data.tests.test_enrollment`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name nested values in small cadmin leaderboard, dashboard integration,
  and deadline-reminder tests before client calls or assertions. Verification:
  `uv run ruff check cadmin/tests/test_leaderboard_views.py courses/tests/test_dashboard_integration.py courses/tests/test_deadline_reminder_dry_run.py courses/tests/test_deadline_reminder_homework.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_leaderboard_views courses.tests.test_dashboard_integration courses.tests.test_deadline_reminder_dry_run courses.tests.test_deadline_reminder_homework`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name single nested values in scoring, load-project-data, project-statistics
  admin, Datamailer admin, and enrollment certificate tests. Verification:
  `uv run ruff check courses/tests/scoring_base.py courses/tests/test_load_project_data_script.py courses/tests/test_project_statistics_admin.py data/tests/test_datamailer_admin.py data/tests/test_enrollment_certificates.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_scoring courses.tests.test_load_project_data_script courses.tests.test_project_statistics_admin data.tests.test_datamailer_admin data.tests.test_enrollment_certificates`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name URLs, route coverage values, queryset counts, and pagination checks
  in small API, cadmin, and course tests before assertions or client calls.
  Verification:
  `uv run ruff check api/tests/test_homework_auth.py api/tests/test_openapi.py cadmin/tests/test_homework_submission_edit_views.py courses/tests/test_course_duplication.py courses/tests/test_course_project_submissions.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_homework_auth api.tests.test_openapi cadmin.tests.test_homework_submission_edit_views courses.tests.test_course_duplication courses.tests.test_course_project_submissions`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name deadline deltas, command output, template contexts, cache reads,
  URLs, and pagination checks in small course test modules before assertions,
  render calls, or client calls. Verification:
  `uv run ruff check courses/tests/deadline_reminder_project.py courses/tests/test_datamailer_campaign_command.py courses/tests/test_datamailer_templates.py courses/tests/test_leaderboard.py courses/tests/test_project_eval_view.py courses/tests/test_project_list_view.py courses/tests/test_project_statistics_integration.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_deadline_reminder_project courses.tests.test_datamailer_campaign_command courses.tests.test_datamailer_templates courses.tests.test_leaderboard courses.tests.test_project_eval_view courses.tests.test_project_list_view courses.tests.test_project_statistics_integration`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name homework scoring state checks, Datamailer certificate list keys,
  recipient-list import output buffers, and Datamailer preference payloads
  before assertions, command calls, or mock expectations. Verification:
  `uv run ruff check courses/tests/homework_scoring_view_base.py courses/tests/test_datamailer_certificates.py courses/tests/test_datamailer_recipient_list_imports.py courses/tests/test_datamailer_status.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_scoring_view courses.tests.test_homework_scoring_view_warnings courses.tests.test_datamailer_certificates courses.tests.test_datamailer_recipient_list_imports courses.tests.test_datamailer_status`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name dashboard, project-detail, project-statistics, and project-results
  URLs plus project-score lookup values before client calls or assertions.
  Verification:
  `uv run ruff check courses/tests/test_dashboard_access.py courses/tests/test_project_view.py courses/tests/test_project_statistics_views.py courses/tests/project_score_base.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_dashboard_access courses.tests.test_project_view courses.tests.test_project_statistics_views courses.tests.test_project_score courses.tests.test_project_score_outcomes courses.tests.test_project_score_bonus courses.tests.test_project_results`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name shared project-view URLs, homework optional-field URLs, Datamailer
  registration list keys, Datamailer enabled checks, and campaign payloads
  before client calls, assertions, or request-expectation construction.
  Verification:
  `uv run ruff check courses/tests/project_view_base.py courses/tests/test_homework_optional_fields.py courses/tests/test_datamailer_registration.py courses/tests/test_datamailer_client.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_view courses.tests.test_homework_optional_fields courses.tests.test_datamailer_registration courses.tests.test_datamailer_client`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name cadmin project-submission enrollments and data course criteria
  response values before helper calls, response assertions, or YAML parsing.
  Verification:
  `uv run ruff check cadmin/tests/test_view_models.py data/tests/test_course.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_view_models data.tests.test_course`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name course-list fixture timestamps and text words, Datamailer webhook
  request/response values, leaderboard fixture timestamps, and project export
  expected records before calls or assertions. Verification:
  `uv run ruff check courses/tests/test_course_list.py data/tests/test_datamailer_webhook.py data/tests/test_leaderboard.py data/tests/test_project.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course_list data.tests.test_datamailer_webhook data.tests.test_leaderboard data.tests.test_project`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name API enrollment certificate payloads, response bodies, and
  registration-campaign JSON bodies plus existence checks before client calls
  or assertions. Verification:
  `uv run ruff check api/tests/test_enrollment_exports.py api/tests/test_registration_campaigns.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_enrollment_exports api.tests.test_registration_campaigns`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer homework-score submission timestamps, homework and
  peer-review submitter list keys, peer-review deadline strings, and eval URL
  checks before assertions. Verification:
  `uv run ruff check courses/tests/test_datamailer_homework_scores.py courses/tests/test_datamailer_peer_review.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_homework_scores courses.tests.test_datamailer_peer_review`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name wrapped-view URLs, homework submission URLs, and submission existence
  checks before client calls or assertions. Verification:
  `uv run ruff check courses/tests/test_wrapped_views.py courses/tests/test_homework_submission_validation.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_wrapped_views courses.tests.test_homework_submission_validation`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name admin criteria form validity checks and unit-scoring possible-answer
  strings before assertions or question construction. Verification:
  `uv run ruff check courses/tests/test_admin_criteria_form.py courses/tests/test_unit_scoring.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_admin_criteria_form courses.tests.test_unit_scoring`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name data homework export URLs, expected export records, RDS default
  lookup results, and copy-summary source paths before calls or assertions.
  Verification:
  `uv run ruff check data/tests/test_homework.py courses/tests/test_load_rds_export_script.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_homework courses.tests.test_load_rds_export_script`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name project-statistics existence checks and statistic value lookups
  before assertions. Verification:
  `uv run ruff check courses/tests/test_project_statistics.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_statistics`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer recipient-list keys, command output values, import
  object prefix checks, and import success messages before expectations or
  assertions. Verification:
  `uv run ruff check courses/tests/test_datamailer_recipient_lists.py courses/tests/datamailer_recipient_lists_base.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_recipient_list_imports`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name project-evaluation submit URLs, expected criteria option lists, and
  criteria-response counts before calls or assertions. Verification:
  `uv run ruff check courses/tests/project_eval_base.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_eval courses.tests.test_project_eval_view`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name peer-review badge course URLs, peer-review submissions, submitted
  timestamps, and project-score answer rows before calls or assertions.
  Verification:
  `uv run ruff check courses/tests/test_peer_review_badge.py courses/tests/test_project_score.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_peer_review_badge courses.tests.test_project_score`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name cadmin homework edit, action, course, and homework URLs before
  helper calls, client calls, or template assertions. Verification:
  `uv run ruff check cadmin/tests/homework_view_base.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_homework_views cadmin.tests.test_homework_submission_edit_views`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer contact test output, payload, and tag values before
  assertions or send calls. Verification:
  `uv run ruff check courses/tests/test_datamailer_contact.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_contact`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name wrapped-statistics test dates and row counts before model creation
  or assertions. Verification:
  `uv run ruff check courses/tests/test_wrapped_statistics.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_wrapped_statistics`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name cadmin Datamailer operation and event URLs before client calls or
  assertions. Verification:
  `uv run ruff check cadmin/tests/test_datamailer_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_datamailer_views`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name homework submission view test post data, saved submissions, dates,
  and URLs before helper/client calls. Verification:
  `uv run ruff check courses/tests/test_homework_submission_view.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_submission_view`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name project-evaluation test URLs, post data, counts, and existence
  checks before client/helper calls or assertions. Verification:
  `uv run ruff check courses/tests/test_project_eval.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_eval`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name project-submissions view test due dates and URLs before model
  creation, client calls, or assertions. Verification:
  `uv run ruff check courses/tests/test_project_submissions_view.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_submissions_view`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name course detail test route URLs, calendar counts, and attribute checks
  before client calls or assertions. Verification:
  `uv run ruff check courses/tests/test_course.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name deadline test rounded values, expected datetimes, timezone objects,
  and request users before assertions or namespace construction. Verification:
  `uv run ruff check courses/tests/test_deadlines.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_deadlines`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name project-voting test due dates, URLs, vote counts, and existence
  checks before model/client calls or assertions. Verification:
  `uv run ruff check courses/tests/test_project_voting.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_voting`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name homework submission integration due dates, URLs, expected fields,
  post data, and existence checks before model/client calls or assertions.
  Verification:
  `uv run ruff check courses/tests/test_homework_submission_integrations.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_submission_integrations`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name shared course-view test helper URLs, scored-state checks, attribute
  checks, and formatted deadlines before client calls or assertions.
  Verification:
  `uv run ruff check courses/tests/course_view_base.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course courses.tests.test_course_certificates`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name cadmin homework view test submission, edit, enrollment, action, and
  redirect URLs before client calls or assertions. Verification:
  `uv run ruff check cadmin/tests/test_homework_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_homework_views`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer membership test users, list keys, and expected key lists
  before helper calls, value-object construction, or assertions. Verification:
  `uv run ruff check courses/tests/test_datamailer_membership.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_membership`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Name Datamailer outbox test error, attempt, status, and command output
  values before retry classification or assertions. Verification:
  `uv run ruff check courses/tests/test_datamailer_outbox.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox`,
  touched-file nested-call scans report `touched_file_nested_calls=0`,
  `uvx pyrefly check`, and `git diff --check`.
- [x] Remove remaining one-use script wrappers for evaluation-score creation,
  score recalculation, and seed-summary construction while keeping constructed
  values named before append or output. Verification:
  `uv run ruff check scripts/load_project_data.py scripts/generate_production_like_leaderboard_data.py docs/refactoring-plan.md`,
  `python -m py_compile scripts/load_project_data.py scripts/generate_production_like_leaderboard_data.py`,
  broad AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Remove the Datamailer outbox sender dispatch map and tiny one-use sender
  wrappers by making the event-type dispatcher explicit with named payload
  fields. Verification:
  `uv run ruff check course_management/datamailer_outbox_senders.py course_management/urls.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox`,
  broad AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name Django URL includes before `path(...)` registration so the project URL
  module follows the no-nested-meaningful-call cleanup rule. Verification:
  `uv run ruff check course_management/urls.py docs/refactoring-plan.md`,
  broad AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Inline one-use Datamailer outbox dispatch-run and count-initialization
  helpers into the processing coordinator while keeping the created run and count
  dictionary named. Verification:
  `uv run ruff check course_management/datamailer_outbox_runs.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox`,
  broad AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Extract homework-create required-field validation from attribute assembly
  so URL validation, date parsing, slug validation, and record construction are
  easier to scan independently. Verification:
  `uv run ruff check api/views/homework_create.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_homeworks`, broad AST cleanup
  gates report zero violations, `uvx pyrefly check`, and `git diff --check`.
- [x] Replace repeated Datamailer send-total normalization assignments with an
  explicit field tuple and loop, keeping the no-comprehension style while making
  the aggregate fields easier to audit. Verification:
  `uv run ruff check cadmin/views/datamailer_send_audits.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_datamailer_views`, broad AST
  cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name Datamailer campaign command argv lists before `call_command(...)`
  calls so the tests no longer pass long positional command argument lists
  inline. Verification:
  `uv run ruff check courses/tests/test_datamailer_campaign_command.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_campaign_command`,
  broad AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name Datamailer recipient-list import command argv lists before
  `call_command(...)`, including the timeout assertion path. Verification:
  `uv run ruff check courses/tests/test_datamailer_recipient_list_imports.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_list_imports`,
  broad AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Simplify ordered country assembly by extending the remaining country list
  instead of copying both groups with separate append loops. Verification:
  `uv run ruff check courses/registration.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_registration_helpers`, broad
  AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Replace remaining wide positional `datetime(...)` test fixture calls with
  keyword arguments so timestamp fields are explicit and the wide positional call
  scan has no remaining hits. Verification:
  `uv run ruff check courses/tests/test_deadlines.py courses/tests/test_wrapped_statistics.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_deadlines courses.tests.test_wrapped_statistics`,
  broad AST cleanup gates report zero violations, wide positional call scan
  reports zero hits, `uvx pyrefly check`, and `git diff --check`.
- [x] Normalize Datamailer send-status command totals with an explicit field
  tuple and loop, matching the cadmin aggregate cleanup and removing repeated
  assignment blocks. Verification:
  `uv run ruff check data/management/commands/datamailer_send_status.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox`, broad
  AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Extract browser timezone cookie decoding/validation into the timezone
  service and reuse it from account settings and user datetime formatting.
  Verification:
  `uv run ruff check accounts/services/timezones.py accounts/views/account_settings.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_account_settings courses.tests.test_deadlines`,
  broad AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split deadline-reminder command dry-run output and send output loops out of
  the command handler so `handle` remains the planning coordinator. Verification:
  `uv run ruff check courses/management/commands/send_deadline_reminders.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_deadline_reminder_dry_run courses.tests.test_deadline_reminder_homework courses.tests.test_deadline_reminder_project courses.tests.test_deadline_reminder_peer_review`,
  broad AST cleanup gates report zero violations, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split project-vote mutation out of the route response selection so the
  public view coordinates authentication, vote application, and response type
  without carrying the mutation details inline. Verification:
  `uv run ruff check courses/views/project_submission_votes.py courses/tests/test_project_voting.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_voting`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split learning-in-public score reset predicates and total recomputation
  out of the enrollment flag update loops so the bulk-update loops only decide
  which submissions need mutation and persist the affected fields. Verification:
  `uv run ruff check courses/services/enrollment_flags.py courses/tests/test_disable_learning_in_public.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_disable_learning_in_public`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Replace certificate-update lookup parameter groups with a
  `CertificateUpdateLookups` value object and pass that object through the
  application flow instead of expanding it into repeated arguments.
  Verification:
  `uv run ruff check api/views/enrollment_certificate_updates.py data/tests/test_enrollment_certificates.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_enrollment_certificates`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Replace Datamailer certificate availability send argument groups with a
  `CertificateAvailabilitySendData` value object and pass that object through
  readiness, graduate-outcome sync, idempotency-key, and error-handling steps.
  Verification:
  `uv run ruff check course_management/datamailer/sync/certificates.py courses/tests/test_datamailer_certificates.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_certificates`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split Datamailer outbox event dispatch from event-specific send behavior
  by moving each supported event type into a named sender and using a sender
  registry in the dispatcher. Verification:
  `uv run ruff check course_management/datamailer_outbox_senders.py courses/tests/test_datamailer_outbox.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Align homework-create validation with project-create validation by
  introducing a `HomeworkCreateInput` value object for required raw fields and
  passing that object through due-date and slug validation. Verification:
  `uv run ruff check api/views/homework_create.py api/tests/test_homeworks.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_homeworks`, comprehension,
  size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Centralize Datamailer payload email normalization in the payload base
  module and remove duplicated inline `strip().lower()` recipient handling
  from enrollment, submission, peer-review assignment, graduate, and
  certificate-availability payload builders. Verification:
  `uv run ruff check course_management/datamailer/payloads/base.py course_management/datamailer/payloads/submissions.py course_management/datamailer/payloads/peer_review_members.py course_management/datamailer/payloads/certificate_availability.py course_management/datamailer/payloads/course_graduates.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_membership courses.tests.test_datamailer_homework_scores courses.tests.test_datamailer_project_scores courses.tests.test_datamailer_peer_review courses.tests.test_datamailer_certificates`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Group peer-review assignment notification send state in a
  `PeerReviewAssignmentSendData` value object and pass that object through
  readiness and error handling instead of repeatedly threading config,
  list-key, payload, and project identity as separate arguments. Verification:
  `uv run ruff check course_management/datamailer/sync/peer_review_notifications.py courses/tests/test_datamailer_peer_review.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_peer_review`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split most-common homework answer lookup out of the correct-answer fill
  workflow so the fill function coordinates existing-answer guards,
  missing-answer handling, and persistence while the queryset logic lives in a
  named query helper. Verification:
  `uv run ruff check courses/homework_correct_answers.py courses/tests/test_homework_correct_answers.py cadmin/tests/test_homework_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_correct_answers cadmin.tests.test_homework_views`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Reuse the shared Datamailer `add_from_email_if_configured` helper for
  peer-review assignment payloads instead of mutating the sender address inline,
  and cover the configured sender in the peer-review payload test. Verification:
  `uv run ruff check course_management/datamailer/payloads/peer_review.py courses/tests/test_datamailer_peer_review.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_peer_review`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split multiple-choice homework answer formatting into scored-index
  selection and option-list construction helpers so the public formatter reads
  as selected-options, possible answers, correct indices, rendered options, and
  missing-answer annotation. Verification:
  `uv run ruff check courses/views/homework_answers.py courses/tests/test_homework_scoring_view.py courses/tests/test_homework_scoring_view_warnings.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_scoring_view courses.tests.test_homework_scoring_view_warnings`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split project API serialization into identity, settings, deadline, and
  deletion field groups, and avoid counting project submissions twice while
  computing deletion blockers. Verification:
  `uv run ruff check api/views/project_serializers.py api/tests/test_projects.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_projects`, comprehension,
  size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Move project scoring result accumulation into `ProjectScoringResult`
  and name the per-submission scoring-data construction so project scoring no
  longer carries parallel result lists and counters in the main loop.
  Verification:
  `uv run ruff check courses/project_submission_scoring.py courses/tests/test_project_score.py courses/tests/test_project_score_bonus.py api/tests/test_project_scoring.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_score courses.tests.test_project_score_bonus api.tests.test_project_scoring`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split project calendar deadline spec construction from calendar event
  rendering so the project deadline event loop only iterates over named specs
  and renders each event. Verification:
  `uv run ruff check courses/views/course_calendar_events.py courses/tests/test_course.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course`, comprehension,
  size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Share Datamailer route-to-public-URL conversion through a named payload
  URL helper and remove a one-use project score URL wrapper after the shared
  helper made it unnecessary. Verification:
  `uv run ruff check course_management/datamailer/payloads/urls.py course_management/datamailer/payloads/score_notifications.py course_management/datamailer/payloads/peer_review.py course_management/datamailer/payloads/project_scores.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_homework_scores courses.tests.test_datamailer_project_scores courses.tests.test_datamailer_peer_review`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Reuse the shared Datamailer route-to-public-URL helper across certificate,
  submission, registration, and peer-review member payloads while leaving stored
  certificate paths as direct public URL conversion. Verification:
  `uv run ruff check course_management/datamailer/payloads/certificate_availability.py course_management/datamailer/payloads/submissions.py course_management/datamailer/payloads/registration_campaigns.py course_management/datamailer/payloads/registration_confirmations.py course_management/datamailer/payloads/peer_review_members.py course_management/datamailer/payloads/urls.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_certificates courses.tests.test_datamailer_registration cadmin.tests.test_campaign_views courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_peer_review`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name Datamailer status display values, selected superuser records, and
  generated leaderboard course date boundaries before returning tuple records.
  Verification:
  `uv run ruff check courses/management/commands/datamailer_status.py scripts/create_superuser.py scripts/generate_production_like_leaderboard_data.py courses/tests/test_datamailer_status.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_status`,
  `uv run python -m py_compile scripts/create_superuser.py scripts/generate_production_like_leaderboard_data.py`,
  repo-wide tuple-record direct-call scan reports `total=0`, comprehension,
  size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Replace immediate one-off tuple aliases before loops with direct tuple
  iteration in course API serialization/mutation helpers and Datamailer
  commands. Verification:
  `uv run ruff check api/views/course_serializers.py api/views/course_mutations.py courses/management/commands/datamailer_campaign.py courses/management/commands/sync_datamailer_contacts.py api/tests/test_courses.py courses/tests/test_datamailer_campaign_command.py courses/tests/test_datamailer_contact.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_courses courses.tests.test_datamailer_campaign_command courses.tests.test_datamailer_contact`,
  touched-file one-off literal-alias scan reports
  `touched_file_one_off_literal_aliases=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Replace one-off tuple aliases before loops in account email extraction,
  homework upsert validation/save helpers, Datamailer webhook validation,
  registration-campaign filters, and the public registration form. Verification:
  `uv run ruff check accounts/auth.py api/views/homework_upsert_validation.py api/views/homework_upsert_save.py api/views/datamailer_webhook_validation.py api/views/registration_campaign_registrations.py courses/views/registration_form.py accounts/tests_auth.py api/tests/test_homeworks.py api/tests/test_registration_campaigns.py courses/tests/test_registration_campaigns.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_auth api.tests.test_homeworks api.tests.test_registration_campaigns courses.tests.test_registration_campaigns`,
  touched-file one-off literal-alias scan reports
  `touched_file_one_off_literal_aliases=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Replace remaining immediate list aliases before loops in Datamailer status
  output, recipient-list option tests, project-evaluation assertions, and
  project-statistics score-field assertions. Verification:
  `uv run ruff check courses/management/commands/datamailer_status.py courses/tests/test_datamailer_status.py courses/tests/test_datamailer_recipient_lists.py courses/tests/test_datamailer_recipient_list_audit.py courses/tests/project_eval_base.py courses/tests/test_project_eval.py courses/tests/test_project_eval_view.py courses/tests/test_project_statistics.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_status courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_recipient_list_audit courses.tests.test_project_eval courses.tests.test_project_eval_view courses.tests.test_project_statistics`,
  repo-wide immediate-list-alias scan reports `immediate_list_aliases=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Replace the final immediate tuple aliases before loops in Datamailer
  recipient-list drift and audit helpers. Verification:
  `uv run ruff check course_management/datamailer/recipient_list_drift.py course_management/datamailer/recipient_list_audit.py courses/tests/test_datamailer_recipient_list_audit.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_list_audit`,
  repo-wide immediate literal-alias scan reports
  `immediate_literal_aliases=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Name OpenAPI route sample-value and parameter-marker intermediates before
  replacing generated URL segments. Verification:
  `uv run ruff check api/openapi/spec.py api/tests/test_openapi.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_openapi`,
  production nested-call-argument scan reports
  `production_nested_call_args=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Name account settings form widgets before assigning them in
  `Meta.widgets`, keeping the existing design-system form classes and
  attributes unchanged. Verification:
  `uv run ruff check accounts/forms.py accounts/tests_account_settings.py docs/design-system.md docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_account_settings`,
  touched-file widget dictionary scan reports
  `accounts_forms_dict_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split submission-derived user Wrapped metrics out of
  `user_wrapped_metrics_values` so the top-level metric assembler no longer
  sits on the 30-line production threshold. Verification:
  `uv run ruff check courses/wrapped_statistics/metrics.py courses/tests/test_wrapped_statistics.py courses/tests/test_wrapped_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_wrapped_statistics courses.tests.test_wrapped_views`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, and `touched_dict_call_values=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split the incomplete-project redirect branch out of the project
  statistics view so the main view stays focused on lookup, guard, calculation,
  and render. Verification:
  `uv run ruff check courses/views/project_statistics.py courses/tests/test_project_statistics_views.py courses/tests/test_project_statistics_integration.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_statistics_views courses.tests.test_project_statistics_integration`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, and `touched_wide_positional_calls=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split project-evaluation review-state context assembly out of
  `project_eval_build_context` so the page context builder composes page
  objects with a named review context fragment. Verification:
  `uv run ruff check courses/views/project_eval_submit_context.py courses/tests/test_project_eval.py courses/tests/test_project_eval_view.py courses/tests/project_eval_base.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_eval courses.tests.test_project_eval_view`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, and `touched_wide_positional_calls=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name volunteer review-only project-submission defaults before passing
  them into optional project-evaluation submission creation. Verification:
  `uv run ruff check courses/views/project_eval_actions.py courses/tests/test_project_assign.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_assign`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split dashboard project quartile metric fields out of the project stats
  summary assembler so completion/pass-fail totals and quartile fields have
  separate names. Verification:
  `uv run ruff check courses/views/dashboard_projects.py courses/tests/test_dashboard_project_stats.py courses/tests/test_dashboard.py courses/tests/test_dashboard_integration.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_dashboard_project_stats courses.tests.test_dashboard courses.tests.test_dashboard_integration`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Simplify homework submission summary field assembly by removing the
  intermediate optional-field list and adding visible fields directly while
  preserving the existing confirmation payload order. Verification:
  `uv run ruff check courses/views/homework_submission_summary.py courses/tests/test_homework_submission_integrations.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_submission_integrations`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split peer-review assignment selection into setup, all-reviewer
  iteration, per-reviewer selection, project-index selection, and assignment
  construction. Added a `ReviewerAssignmentData` value object so reviewer
  selection passes one named context instead of four positional arguments.
  Verification:
  `uv run ruff check courses/project_assignment_selection.py courses/tests/test_unit_projects.py courses/tests/test_project_assign.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_unit_projects courses.tests.test_project_assign`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Move homework and project statistics display section construction into
  `courses.models.stat_display`, naming each `StatSection` before appending
  and leaving model `get_stat_fields` methods as short orchestration. The
  project section order remains project metrics, peer-review metrics, then
  total/time metrics. Verification:
  `uv run ruff check courses/models/stat_display.py courses/models/homework.py courses/models/project.py courses/tests/test_project_statistics.py courses/tests/test_dashboard.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_statistics courses.tests.test_dashboard`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Share the leaderboard enrollment lookup between score breakdown and
  complaint views so both detail views use one named domain lookup and the
  complaint view no longer carries query construction inline. Verification:
  `uv run ruff check courses/views/course_leaderboard.py courses/tests/test_course_leaderboard_complaints.py courses/tests/test_course_leaderboard_score_breakdown.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course_leaderboard_complaints courses.tests.test_course_leaderboard_score_breakdown`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split certificate update delivery from certificate update processing so
  validation, lookup, application, persistence, and notification each have a
  named step. Verification:
  `uv run ruff check api/views/enrollment_certificate_updates.py api/tests/test_enrollment_exports.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_enrollment_exports`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split project creation attribute assembly into validated create values
  and final model attributes so required field/date/slug validation is separate
  from the `Project.objects.create` payload. Verification:
  `uv run ruff check api/views/project_create.py api/tests/test_projects.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_projects`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split Datamailer campaign action data construction out of the campaign
  action handler so the handler only resolves the client, builds action data,
  and runs the guarded action. Verification:
  `uv run ruff check cadmin/views/campaign_datamailer.py cadmin/tests/test_campaign_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_campaign_views`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split registration confirmation Datamailer delivery fields from rendered
  context and metadata so the payload builder composes named envelope/content
  pieces instead of returning one large inline dictionary. Verification:
  `uv run ruff check course_management/datamailer/payloads/registration_confirmations.py courses/tests/test_datamailer_registration.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_registration`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split peer-review assignment Datamailer delivery fields from context,
  list, member, and metadata payload content so the notification payload is
  assembled from named pieces. Verification:
  `uv run ruff check course_management/datamailer/payloads/peer_review.py courses/tests/test_datamailer_peer_review.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_peer_review`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split Datamailer send audit base defaults into send identity defaults
  and outcome defaults so list/template/category fields are separate from
  status/source/error/response fields. Verification:
  `uv run ruff check course_management/datamailer/sync/audit.py courses/tests/test_datamailer_contact.py courses/tests/test_datamailer_registration.py courses/tests/test_datamailer_peer_review.py courses/tests/test_datamailer_homework_scores.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_contact courses.tests.test_datamailer_registration courses.tests.test_datamailer_peer_review courses.tests.test_datamailer_homework_scores`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split Datamailer recipient-list batch syncing into batch iteration,
  import-job data construction, inline sync result construction, and result
  writing so the per-batch import-vs-inline decision is isolated. Verification:
  `uv run ruff check course_management/datamailer/recipient_list_sync.py courses/tests/test_datamailer_recipient_lists.py courses/tests/test_datamailer_recipient_list_imports.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_recipient_list_imports`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split OpenAPI spec assembly into named info, security scheme, and
  components helpers so `build_openapi_spec` composes the top-level document
  instead of carrying all nested sections inline. Verification:
  `uv run ruff check api/openapi/spec.py api/tests/test_openapi.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_openapi`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split Datamailer recipient-list audit run data construction out of the
  management command handler so the handler validates options, builds batches,
  creates audit run data, executes the audit, and handles drift. Verification:
  `uv run ruff check courses/management/commands/audit_datamailer_recipient_lists.py courses/tests/test_datamailer_recipient_list_audit.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_list_audit`,
  touched-file scans report `touched_long_functions=0`,
  `touched_nested_call_args=0`, `touched_dict_call_values=0`, and
  `touched_wide_positional_calls=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split `scripts/load_rds_export.py` target CLI options into path and
  behavior groups, and split table-copy plan construction into named plan and
  column-copy data builders. Also named remaining nested call arguments in the
  touched script. Verification:
  `uv run ruff check scripts/load_rds_export.py courses/tests/test_load_rds_export_script.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_load_rds_export_script`,
  `python -m py_compile scripts/load_rds_export.py`, touched-file scans report
  `touched_long_functions=0`, `touched_nested_call_args=0`,
  `touched_dict_call_values=0`, and `touched_wide_positional_calls=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Split `scripts/load_project_data.py` enrollment and project default
  assembly into named base/optional/review helpers, keeping model-field
  filtering in the enrollment builder. Verification:
  `uv run ruff check scripts/load_project_data.py courses/tests/test_load_project_data_script.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_load_project_data_script`,
  `python -m py_compile scripts/load_project_data.py`, touched-file scans
  report `touched_long_functions=0`, `touched_nested_call_args=0`,
  `touched_dict_call_values=0`, and `touched_wide_positional_calls=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Remove unused `__all__` export lists from Datamailer client and key
  modules after confirming no wildcard imports depend on them. Verification:
  `uv run ruff check course_management/datamailer/client.py course_management/datamailer/keys.py courses/tests/test_datamailer_client.py courses/tests/test_datamailer_recipient_lists.py courses/tests/test_datamailer_homework_scores.py courses/tests/test_datamailer_project_scores.py courses/tests/test_datamailer_registration.py courses/tests/test_datamailer_certificates.py courses/tests/test_datamailer_contact.py courses/tests/test_datamailer_peer_review.py`,
  `uv run python manage.py test courses.tests.test_datamailer_client courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_homework_scores courses.tests.test_datamailer_project_scores courses.tests.test_datamailer_registration courses.tests.test_datamailer_certificates courses.tests.test_datamailer_contact courses.tests.test_datamailer_peer_review`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name Django bootstrap path strings in maintained scripts instead of
  nesting `str(project_root)` inside `sys.path.insert(...)`. Verification:
  `uv run ruff check scripts/score_project.py scripts/debug_score_project.py scripts/score_project_dev.py scripts/create_superuser.py scripts/generate_production_like_leaderboard_data.py scripts/move_criteria.py scripts/analyze_scoring_bug.py`,
  `python -m py_compile scripts/score_project.py scripts/debug_score_project.py scripts/score_project_dev.py scripts/create_superuser.py scripts/generate_production_like_leaderboard_data.py scripts/move_criteria.py scripts/analyze_scoring_bug.py`,
  script nested-call scan reports zero hits, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Name the OpenAPI graduate item schema and graduates array before adding
  them to the integration schema dictionary. Verification:
  `uv run ruff check api/openapi/integration_schemas.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scan
  reports `touched_dict_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract Course and Registration OpenAPI model-derived schemas from the
  large schema map into named constants, including repeated registration
  campaign properties. Verification:
  `uv run ruff check api/openapi/course_schemas.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scan
  reports `touched_dict_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract generated OpenAPI content enum schemas into named constants
  before assembling the enum schema map. Verification:
  `uv run ruff check api/openapi/content_schemas/enums.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scan
  reports `touched_dict_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract OpenAPI question schema property groups, enum refs, string
  arrays, and error arrays into named constants before assembling the question
  schema map. Verification:
  `uv run ruff check api/openapi/content_schemas/questions.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scans
  report `touched_dict_call_values=0` and
  `touched_sequence_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract OpenAPI homework summary/detail, property groups, shared arrays,
  and `allOf`/`oneOf` lists into named constants before assembling the homework
  schema map. Verification:
  `uv run ruff check api/openapi/content_schemas/homeworks.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scans
  report `touched_dict_call_values=0` and
  `touched_sequence_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract OpenAPI project summary/detail, property groups, shared arrays,
  and `allOf`/`oneOf` lists into named constants before assembling the project
  schema map. Verification:
  `uv run ruff check api/openapi/content_schemas/projects.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scans
  report `touched_dict_call_values=0` and
  `touched_sequence_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract OpenAPI question-path response objects into named constants
  before assembling operation response maps. Verification:
  `uv run ruff check api/openapi/content_paths/questions.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scans
  report `touched_dict_call_values=0` and
  `touched_sequence_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract OpenAPI homework-path response objects into named constants
  before assembling operation response maps. Verification:
  `uv run ruff check api/openapi/content_paths/homeworks.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scans
  report `touched_dict_call_values=0` and
  `touched_sequence_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract OpenAPI project-path response objects into named constants
  before assembling operation response maps. Verification:
  `uv run ruff check api/openapi/content_paths/projects.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scans
  report `touched_dict_call_values=0` and
  `touched_sequence_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract OpenAPI data-path response objects into named constants before
  assembling operation response maps. Verification:
  `uv run ruff check api/openapi/data_paths.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scans
  report `touched_dict_call_values=0` and
  `touched_sequence_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Extract OpenAPI course and registration-campaign path response objects
  into named constants before assembling operation response maps.
  Verification:
  `uv run ruff check api/openapi/course_paths.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, touched-file scans
  report `touched_dict_call_values=0` and
  `touched_sequence_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Name OpenAPI request-body JSON content before assembling the request
  body dictionary, completing the OpenAPI inline-call cleanup pass.
  Verification:
  `uv run ruff check api/openapi/primitives.py api/tests/test_openapi.py`,
  `uv run python manage.py test api.tests.test_openapi`, OpenAPI scans report
  `openapi_dict_call_values=0` and `openapi_sequence_call_values=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Name serialized timestamp values before assembling JSON export records
  in `scripts/pull_project_data.py`. Verification:
  `uv run ruff check scripts/pull_project_data.py`,
  `python -m py_compile scripts/pull_project_data.py`, touched-file scan
  reports `touched_dict_call_values=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Name generated descriptions, URLs, and parsed due dates before assembling
  course/homework/project defaults in the production-like leaderboard data
  generator. Verification:
  `uv run ruff check scripts/generate_production_like_leaderboard_data.py`,
  `python -m py_compile scripts/generate_production_like_leaderboard_data.py`,
  touched-file scans report `touched_dict_call_values=0` and
  `touched_long_functions=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Name the optional admin user id string and append superuser command
  arguments one token at a time in `scripts/load_rds_export.py`. Verification:
  `uv run ruff check scripts/load_rds_export.py courses/tests/test_load_rds_export_script.py`,
  `uv run python manage.py test courses.tests.test_load_rds_export_script`,
  `python -m py_compile scripts/load_rds_export.py`, touched-file scan reports
  `touched_sequence_call_values=0` and
  `touched_append_extend_constructed=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Name the social-login email address list before constructing the auth
  test helper namespace. Verification:
  `uv run ruff check accounts/tests_auth.py`,
  `uv run python manage.py test accounts.tests_auth`, touched-file scans
  report `touched_nested_call_args=0` and `touched_long_functions=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Remove the enrollment graduate test helper that unpacked
  `PassedProjectSubmissionData` fields back into positional arguments; callers
  now construct the dataclass and pass it directly. Verification:
  `uv run ruff check data/tests/enrollment_base.py data/tests/test_enrollment.py`,
  `uv run python manage.py test data.tests.test_enrollment`, touched-file
  scans report `touched_wide_helpers=0` and `touched_nested_call_args=0`,
  comprehension, size-threshold, append-construction, tuple-unpacking, and
  wide-positional-call cleanup gates report zero violations with the 30-line
  production threshold and 60-line test threshold, `uvx pyrefly check`, and
  `git diff --check`.
- [x] Remove the peer-review deadline-reminder test helper that unpacked
  `ProjectSubmissionData` fields back into positional arguments; callers now
  construct the dataclass and pass it directly. Verification:
  `uv run ruff check courses/tests/deadline_reminder_peer_review.py courses/tests/test_deadline_reminder_peer_review.py`,
  `uv run python manage.py test courses.tests.test_deadline_reminder_peer_review`,
  touched-file scans report `touched_wide_helpers=0` and
  `touched_nested_call_args=0`, comprehension, size-threshold,
  append-construction, tuple-unpacking, and wide-positional-call cleanup gates
  report zero violations with the 30-line production threshold and 60-line test
  threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Replace the remaining five-argument test fixture helpers with named
  leaderboard complaint, leaderboard enrollment, and passed-submission actor
  data objects. Verification:
  `uv run ruff check cadmin/tests/test_leaderboard_views.py data/tests/test_leaderboard.py data/tests/test_enrollment_passed.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_leaderboard_views data.tests.test_leaderboard data.tests.test_enrollment_passed`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split the public leaderboard endpoint tests into shared fixtures, core
  response/content tests, cache tests, and pagination tests. Verification:
  `uv run ruff check data/tests/leaderboard_base.py data/tests/test_leaderboard.py data/tests/test_leaderboard_cache.py data/tests/test_leaderboard_pagination.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_leaderboard data.tests.test_leaderboard_cache data.tests.test_leaderboard_pagination`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split Datamailer client endpoint-case construction out of the endpoint
  test class and into contact, recipient-list, transactional, and campaign case
  modules. Verification:
  `uv run ruff check courses/tests/test_datamailer_client.py courses/tests/datamailer_client_cases docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_client`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split homework submission integration tests into confirmation and
  Learning in Public duplicate-link modules, with shared setup and assertion
  helpers grouped by responsibility. Verification:
  `uv run ruff check courses/tests/homework_submission_integration_base.py courses/tests/homework_submission_confirmation_helpers.py courses/tests/homework_submission_learning_links_helpers.py courses/tests/test_homework_submission_integrations.py courses/tests/test_homework_submission_learning_links.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_submission_integrations courses.tests.test_homework_submission_learning_links`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split Datamailer membership tests into shared membership fixtures,
  add/upsert tests, removal tests, and project-passed outcome tests.
  Verification:
  `uv run ruff check courses/tests/datamailer_membership_base.py courses/tests/test_datamailer_membership.py courses/tests/test_datamailer_membership_removals.py courses/tests/test_datamailer_membership_outcomes.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_membership courses.tests.test_datamailer_membership_removals courses.tests.test_datamailer_membership_outcomes`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split registration-campaign public tests into shared campaign fixtures,
  registration-page/form tests, course-page prompt tests, and Datamailer
  notification tests. Verification:
  `uv run ruff check courses/tests/registration_campaign_base.py courses/tests/test_registration_campaigns.py courses/tests/test_registration_campaign_course_page.py courses/tests/test_registration_campaign_notifications.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_registration_campaigns courses.tests.test_registration_campaign_course_page courses.tests.test_registration_campaign_notifications`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split homework API tests into list/create, detail/mutation, and deletion
  modules while reusing the existing homework API fixture base. Verification:
  `uv run ruff check api/tests/test_homeworks.py api/tests/test_homework_mutations.py api/tests/test_homework_deletion.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_homeworks api.tests.test_homework_mutations api.tests.test_homework_deletion`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split Datamailer contact tests into shared contact fixtures, contact
  payload/sync tests, transactional email tests, send-count tests, and contact
  backfill command tests. Verification:
  `uv run ruff check courses/tests/datamailer_contact_base.py courses/tests/test_datamailer_contact.py courses/tests/test_datamailer_transactional.py courses/tests/test_datamailer_send_counts.py courses/tests/test_datamailer_contact_backfill.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_contact courses.tests.test_datamailer_transactional courses.tests.test_datamailer_send_counts courses.tests.test_datamailer_contact_backfill`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split project assignment tests into shared project-action fixtures,
  peer-review assignment tests, and optional evaluation add/delete tests.
  Verification:
  `uv run ruff check courses/tests/project_assign_base.py courses/tests/test_project_assign.py courses/tests/test_project_optional_eval.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_assign courses.tests.test_project_optional_eval`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split homework submission validation tests into shared validation
  fixtures, FAQ/homework URL validation, closed-homework behavior, time-field
  parsing, and Learning in Public URL validation modules. Verification:
  `uv run ruff check courses/tests/homework_submission_validation_base.py courses/tests/test_homework_submission_validation.py courses/tests/test_homework_submission_closed.py courses/tests/test_homework_submission_time_fields.py courses/tests/test_homework_submission_learning_public_validation.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_submission_validation courses.tests.test_homework_submission_closed courses.tests.test_homework_submission_time_fields courses.tests.test_homework_submission_learning_public_validation`,
  repository cleanup gates report zero five-argument helpers, comprehensions,
  size-threshold violations, append-construction violations, tuple-unpacking
  violations, and wide positional calls with the 30-line production threshold
  and 60-line test threshold, `uvx pyrefly check`, and `git diff --check`.
- [x] Split cadmin campaign tests into shared campaign fixtures, registration
  landing-page admin tests, and Datamailer campaign action tests. Verification:
  `uv run ruff check cadmin/tests/campaign_view_base.py cadmin/tests/test_campaign_views.py cadmin/tests/test_campaign_datamailer_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_campaign_views cadmin.tests.test_campaign_datamailer_views`.
- [x] Split Datamailer project score tests into shared score fixtures, project
  score payload tests, and passed-outcome recipient-list/send tests.
  Verification:
  `uv run ruff check courses/tests/datamailer_project_score_base.py courses/tests/test_datamailer_project_scores.py courses/tests/test_datamailer_project_outcomes.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_project_scores courses.tests.test_datamailer_project_outcomes`.
- [x] Split project statistics tests into shared statistics fixtures, raw
  calculation tests, and model creation/update tests. Verification:
  `uv run ruff check courses/tests/project_statistics_base.py courses/tests/test_project_statistics.py courses/tests/test_project_statistics_model.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_statistics courses.tests.test_project_statistics_model`.
- [x] Split course-detail tests into focused authentication, link/calendar,
  homework display, project display, enrollment, and dashboard-link modules.
  Verification:
  `uv run ruff check courses/tests/test_course.py courses/tests/test_course_links.py courses/tests/test_course_calendar.py courses/tests/test_course_homework_display.py courses/tests/test_course_projects.py courses/tests/test_course_enrollment.py courses/tests/test_course_dashboard_link.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course courses.tests.test_course_links courses.tests.test_course_calendar courses.tests.test_course_homework_display courses.tests.test_course_projects courses.tests.test_course_enrollment courses.tests.test_course_dashboard_link`.
- [x] Split dashboard tests into shared dashboard fixtures, basic page tests,
  empty/error state tests, homework summary tests, and homework difficulty
  tests. Verification:
  `uv run ruff check courses/tests/dashboard_view_base.py courses/tests/test_dashboard.py courses/tests/test_dashboard_empty.py courses/tests/dashboard_homework_base.py courses/tests/test_dashboard_homework_stats.py courses/tests/test_dashboard_homework_difficulty.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_dashboard courses.tests.test_dashboard_empty courses.tests.test_dashboard_homework_stats courses.tests.test_dashboard_homework_difficulty`.
- [x] Split project API tests into focused list/detail, create, update/upsert,
  and deletion modules. Verification:
  `uv run ruff check api/tests/test_projects.py api/tests/test_project_creation.py api/tests/test_project_updates.py api/tests/test_project_deletion.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_projects api.tests.test_project_creation api.tests.test_project_updates api.tests.test_project_deletion`.
- [x] Split Datamailer homework score tests into shared score fixtures, payload
  tests, and list-send/audit tests. Verification:
  `uv run ruff check courses/tests/datamailer_homework_score_base.py courses/tests/test_datamailer_homework_scores.py courses/tests/test_datamailer_homework_score_send.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_homework_scores courses.tests.test_datamailer_homework_score_send`.
- [x] Split unit homework-answer scoring tests by checkbox, multiple-choice,
  free-form string, numeric, any-answer, and long-answer behavior.
  Verification:
  `uv run ruff check courses/tests/test_unit_scoring.py courses/tests/test_unit_scoring_choice.py courses/tests/test_unit_scoring_free_form_strings.py courses/tests/test_unit_scoring_free_form_numeric.py courses/tests/test_unit_scoring_free_form_any.py courses/tests/test_unit_scoring_free_form_long.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_unit_scoring courses.tests.test_unit_scoring_choice courses.tests.test_unit_scoring_free_form_strings courses.tests.test_unit_scoring_free_form_numeric courses.tests.test_unit_scoring_free_form_any courses.tests.test_unit_scoring_free_form_long`.
- [x] Split course API tests into shared course fixtures, list/auth, create,
  detail, update, and mutation-auth modules. Verification:
  `uv run ruff check api/tests/course_api_base.py api/tests/test_courses.py api/tests/test_course_creation.py api/tests/test_course_detail.py api/tests/test_course_updates.py api/tests/test_course_auth.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_courses api.tests.test_course_creation api.tests.test_course_detail api.tests.test_course_updates api.tests.test_course_auth`.
- [x] Split leaderboard tests into shared leaderboard fixtures, score/cache,
  pagination, current-student, and score-breakdown admin modules.
  Verification:
  `uv run ruff check courses/tests/leaderboard_base.py courses/tests/test_leaderboard.py courses/tests/test_leaderboard_pagination.py courses/tests/test_leaderboard_current_student.py courses/tests/test_leaderboard_score_breakdown_admin.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_leaderboard courses.tests.test_leaderboard_pagination courses.tests.test_leaderboard_current_student courses.tests.test_leaderboard_score_breakdown_admin`.
- [x] Split homework submissions view tests into shared submissions fixtures,
  access, list, admin-link, and hidden-answer modules. Verification:
  `uv run ruff check courses/tests/homework_submissions_base.py courses/tests/test_homework_submissions.py courses/tests/test_homework_submissions_list.py courses/tests/test_homework_submissions_admin_link.py courses/tests/test_homework_submissions_hidden_answers.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_submissions courses.tests.test_homework_submissions_list courses.tests.test_homework_submissions_admin_link courses.tests.test_homework_submissions_hidden_answers`.
- [x] Split project submission view tests into shared project-submission
  helpers, save/update/delete, confirmation, and invalid/closed modules.
  Verification:
  `uv run ruff check courses/tests/project_submission_view_base.py courses/tests/test_project_submission_view.py courses/tests/test_project_submission_confirmation.py courses/tests/test_project_submission_invalid.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_submission_view courses.tests.test_project_submission_confirmation courses.tests.test_project_submission_invalid`.
- [x] Split question API tests into shared question fixtures, list/detail,
  creation, update, deletion, and mutation-auth modules. Verification:
  `uv run ruff check api/tests/question_api_base.py api/tests/test_questions.py api/tests/test_question_creation.py api/tests/test_question_updates.py api/tests/test_question_deletion.py api/tests/test_question_auth.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_questions api.tests.test_question_creation api.tests.test_question_updates api.tests.test_question_deletion api.tests.test_question_auth`.
- [x] Split Datamailer outbox tests into shared outbox fixtures, retry-status,
  contact erase, membership processing, and status-command modules.
  Verification:
  `uv run ruff check courses/tests/datamailer_outbox_base.py courses/tests/test_datamailer_outbox.py courses/tests/test_datamailer_outbox_contacts.py courses/tests/test_datamailer_outbox_memberships.py courses/tests/test_datamailer_outbox_status_commands.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_outbox courses.tests.test_datamailer_outbox_contacts courses.tests.test_datamailer_outbox_memberships courses.tests.test_datamailer_outbox_status_commands`.
- [x] Split course-list tests into shared course-list fixtures, visibility,
  metadata, assignment-panel, and registration modules. Verification:
  `uv run ruff check courses/tests/course_list_base.py courses/tests/test_course_list.py courses/tests/test_course_list_metadata.py courses/tests/test_course_list_assignments.py courses/tests/test_course_list_registration.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course_list courses.tests.test_course_list_metadata courses.tests.test_course_list_assignments courses.tests.test_course_list_registration`.
- [x] Split Datamailer status tests into shared fixtures, preference, sync, and
  status-command modules. Verification:
  `uv run ruff check courses/tests/datamailer_status_base.py courses/tests/test_datamailer_preferences.py courses/tests/test_datamailer_sync_status.py courses/tests/test_datamailer_status.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_status courses.tests.test_datamailer_preferences courses.tests.test_datamailer_sync_status`.
- [x] Split Datamailer webhook tests into shared webhook fixtures, auth/contact,
  preference, event, and callback-status modules. Verification:
  `uv run ruff check data/tests/datamailer_webhook_base.py data/tests/test_datamailer_webhook.py data/tests/test_datamailer_webhook_events.py data/tests/test_datamailer_webhook_preferences.py data/tests/test_datamailer_callback_status.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_datamailer_webhook data.tests.test_datamailer_webhook_events data.tests.test_datamailer_webhook_preferences data.tests.test_datamailer_callback_status`.
- [x] Split wrapped-statistics tests into shared fixture mixins, platform,
  user-statistic, and recalculation modules. Verification:
  `uv run ruff check courses/tests/wrapped_statistics_base.py courses/tests/test_wrapped_statistics.py courses/tests/test_wrapped_user_statistics.py courses/tests/test_wrapped_recalculation.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_wrapped_statistics courses.tests.test_wrapped_user_statistics courses.tests.test_wrapped_recalculation`.
- [x] Split homework API mutation tests into detail, ID patch, slug patch, and
  by-slug upsert modules. Verification:
  `uv run ruff check api/tests/test_homework_mutations.py api/tests/test_homework_upserts.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_homework_mutations api.tests.test_homework_upserts`.
- [x] Split homework data export tests into shared fixture, factory,
  expectation, and assertion helpers plus a focused endpoint test. Verification:
  `uv run ruff check data/tests/homework_base.py data/tests/test_homework.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_homework`.
- [x] Split cadmin impersonation tests into shared setup, login-as, stop/banner,
  CSRF, and enrollment-button modules. Verification:
  `uv run ruff check cadmin/tests/impersonation_base.py cadmin/tests/test_impersonation_views.py cadmin/tests/test_impersonation_stop_views.py cadmin/tests/test_impersonation_enrollment_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_impersonation_views cadmin.tests.test_impersonation_stop_views cadmin.tests.test_impersonation_enrollment_views`.
- [x] Split enrollment certificate export API tests into shared setup, success,
  mixed-error, and auth modules. Verification:
  `uv run ruff check api/tests/enrollment_exports_base.py api/tests/test_enrollment_exports.py api/tests/test_enrollment_export_errors.py api/tests/test_enrollment_export_auth.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_enrollment_exports api.tests.test_enrollment_export_errors api.tests.test_enrollment_export_auth`.
- [x] Split project-list view tests into shared fixtures, authenticated/list
  rendering, link rendering, and pagination modules. Verification:
  `uv run ruff check courses/tests/project_list_view_base.py courses/tests/test_project_list_view.py courses/tests/test_project_list_pagination.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_list_view courses.tests.test_project_list_pagination`.
- [x] Split project data export tests into shared fixture, factory,
  expectation, and assertion helpers plus a focused endpoint test. Verification:
  `uv run ruff check data/tests/project_base.py data/tests/test_project.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_project`.
- [x] Split course criteria YAML export tests into shared criteria fixtures,
  success, and edge-case modules while removing unused auth setup. Verification:
  `uv run ruff check data/tests/course_criteria_base.py data/tests/test_course.py data/tests/test_course_criteria_yaml_edges.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_course data.tests.test_course_criteria_yaml_edges`.
- [x] Split registration-campaign API tests into shared campaign helpers,
  mutation/statistics tests, and auth/staff-token tests. Verification:
  `uv run ruff check api/tests/registration_campaign_base.py api/tests/test_registration_campaigns.py api/tests/test_registration_campaign_auth.py docs/refactoring-plan.md`,
  `uv run python manage.py test api.tests.test_registration_campaigns api.tests.test_registration_campaign_auth`.
- [x] Split account settings tests into shared settings helpers plus auth,
  overview/profile, and timezone modules. Verification:
  `uv run ruff check accounts/tests_account_settings_base.py accounts/tests_account_settings.py accounts/tests_account_timezone.py docs/refactoring-plan.md`,
  `uv run python manage.py test accounts.tests_account_settings accounts.tests_account_timezone`.
- [x] Split leaderboard data export tests into core response, homework export,
  and project export modules. Verification:
  `uv run ruff check data/tests/test_leaderboard.py data/tests/test_leaderboard_homework.py data/tests/test_leaderboard_projects.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_leaderboard data.tests.test_leaderboard_homework data.tests.test_leaderboard_projects`.
- [x] Split enrollment certificate update tests into mixed bulk, array payload,
  and notification modules. Verification:
  `uv run ruff check data/tests/test_enrollment_certificates.py data/tests/test_enrollment_certificate_notifications.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_enrollment_certificates data.tests.test_enrollment_certificate_notifications`.
- [x] Split passed-enrollment helper tests into shared scenario builders,
  threshold checks, and boundary checks. Verification:
  `uv run ruff check data/tests/enrollment_passed_base.py data/tests/test_enrollment_passed.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_enrollment_passed`.
- [x] Split URL validation unit tests into FAQ contribution, status validation,
  and error-message classes while removing unused logging setup. Verification:
  `uv run ruff check courses/tests/test_unit_url_validation.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_unit_url_validation`.
- [x] Split the shared homework detail view test base into focused fixture,
  request, option, submission, and assertion mixins while keeping the public
  base class stable. Verification:
  `uv run ruff check courses/tests/homework_view_base.py courses/tests/test_homework.py courses/tests/test_homework_submission_view.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework courses.tests.test_homework_submission_view`.
- [x] Split the shared cadmin homework view test base into focused user,
  course/submission, question, edit, assertion, and action mixins while keeping
  the public base class stable. Verification:
  `uv run ruff check cadmin/tests/homework_view_base.py cadmin/tests/test_homework_views.py cadmin/tests/test_homework_submission_edit_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_homework_views cadmin.tests.test_homework_submission_edit_views`.
- [x] Split the shared course detail view test base into focused fixture,
  request, homework assertion, enrollment assertion, ordering, and project
  review mixins while keeping the public base class stable. Verification:
  `uv run ruff check courses/tests/course_view_base.py courses/tests/test_course.py courses/tests/test_course_projects.py courses/tests/test_course_homework_display.py courses/tests/test_course_dashboard_link.py courses/tests/test_course_calendar.py courses/tests/test_course_links.py courses/tests/test_course_enrollment.py courses/tests/test_course_certificates.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course courses.tests.test_course_projects courses.tests.test_course_homework_display courses.tests.test_course_dashboard_link courses.tests.test_course_calendar courses.tests.test_course_links courses.tests.test_course_enrollment courses.tests.test_course_certificates`.
- [x] Split the shared course leaderboard view test base into focused course,
  homework, project, leaderboard, request, assertion, and score-breakdown
  mixins while keeping the public base class stable. Also removed a one-off
  loop alias and named leaderboard records before dictionary construction.
  Verification:
  `uv run ruff check courses/tests/course_leaderboard_base.py courses/tests/test_course_leaderboard.py courses/tests/test_course_leaderboard_score_breakdown.py courses/tests/test_course_leaderboard_complaints.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course_leaderboard courses.tests.test_course_leaderboard_score_breakdown courses.tests.test_course_leaderboard_complaints`.
- [x] Split the shared project evaluation test base into focused project
  fixture, review criteria, request, review state, criteria expectation, and
  review assertion mixins while keeping the public base class stable. Also
  named criteria responses and updated-answer data before dictionary
  construction. Verification:
  `uv run ruff check courses/tests/project_eval_base.py courses/tests/test_project_eval.py courses/tests/test_project_eval_view.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_eval courses.tests.test_project_eval_view`.
- [x] Split the shared homework scoring test base into focused answer,
  course/homework, question, student, scoring assertion, answer-set,
  extra-field, and leaderboard mixins while keeping the public base class
  stable. Also replaced a one-off `zip(...)` loop alias with a direct loop
  iterable. Verification:
  `uv run ruff check courses/tests/scoring_base.py courses/tests/test_scoring.py courses/tests/test_scoring_leaderboard.py courses/tests/test_homework_correct_answers.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_scoring courses.tests.test_scoring_leaderboard courses.tests.test_homework_correct_answers`.
- [x] Split optional homework submission-field tests into focused full-field
  and empty-field scenario classes with shared fixture, request, setup,
  post-data, and assertion mixins. Verification:
  `uv run ruff check courses/tests/test_homework_optional_fields.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_optional_fields`.
- [x] Split project submissions view tests into focused access, display,
  admin-link, peer-review, and copy-email scenario classes with shared fixture,
  request, data, and peer-review helper mixins. Also removed unused logging and
  local model imports. Verification:
  `uv run ruff check courses/tests/test_project_submissions_view.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_submissions_view`.
- [x] Split the shared project view test base into focused fixture, request,
  submission persistence, submission assertion, confirmation email, and
  submission-field assertion mixins while keeping the public base class stable.
  Also named project confirmation learning-link payload before construction.
  Verification:
  `uv run ruff check courses/tests/project_view_base.py courses/tests/project_submission_view_base.py courses/tests/test_project_view.py courses/tests/test_project_submission_view.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_view courses.tests.test_project_submission_view`.
- [x] Split the shared project score test base into focused fixture,
  peer-review fixture, score submission, scoring assertion, reverse-review,
  checkbox, and results-view mixins while keeping the public base class stable.
  Verification:
  `uv run ruff check courses/tests/project_score_base.py courses/tests/test_project_score.py courses/tests/test_project_score_bonus.py courses/tests/test_project_results.py courses/tests/test_project_score_outcomes.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_score courses.tests.test_project_score_bonus courses.tests.test_project_results courses.tests.test_project_score_outcomes`.
- [x] Split project statistics integration tests into focused class fixture,
  instance fixture, workflow data, assertion, and navigation mixins while
  keeping the concrete integration test case stable. Verification:
  `uv run ruff check courses/tests/test_project_statistics_integration.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_statistics_integration`.
- [x] Split cadmin homework view tests into focused submission-view,
  action-redirect, search, and scoring-action scenario classes while reusing
  the shared cadmin homework base. Verification:
  `uv run ruff check cadmin/tests/test_homework_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_homework_views`.
- [x] Split the shared Datamailer recipient-list command test base into
  fixture, bulk-upsert assertion, import setup, registration-import assertion,
  and import-polling mixins while keeping the public base class stable.
  Verification:
  `uv run ruff check courses/tests/datamailer_recipient_lists_base.py courses/tests/test_datamailer_recipient_lists.py courses/tests/test_datamailer_recipient_list_imports.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_recipient_list_imports`.
- [x] Split Datamailer recipient-list import command tests into focused import
  creation, polling success, polling failure, timeout, and validation scenario
  classes, and reused the shared registration fixture instead of local model
  setup. Verification:
  `uv run ruff check courses/tests/test_datamailer_recipient_list_imports.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_list_imports`.
- [x] Split dashboard project statistics tests into shared fixture/submission
  helpers plus focused statistics, completion-rate, enrollment-score, and
  graduate-count scenario classes. Verification:
  `uv run ruff check courses/tests/test_dashboard_project_stats.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_dashboard_project_stats`.
- [x] Split Datamailer peer-review tests into shared fixture and assertion
  mixins plus focused payload, preview-command, and notification-send scenario
  classes. Verification:
  `uv run ruff check courses/tests/test_datamailer_peer_review.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_peer_review`.
- [x] Split cadmin Datamailer view tests into shared operations, requeue, and
  contact-event helpers plus focused operations access/page/requeue and events
  access/page/filter scenario classes. Also named requeue event records before
  building the return dictionary. Verification:
  `uv run ruff check cadmin/tests/test_datamailer_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_datamailer_views`.
- [x] Split the shared homework scoring view test base into focused
  course/homework fixture, question fixture, request, submission/scoring, and
  scored-answer assertion mixins while keeping the public base class stable.
  Verification:
  `uv run ruff check courses/tests/homework_scoring_view_base.py courses/tests/test_homework_scoring_view.py courses/tests/test_homework_scoring_view_warnings.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_scoring_view courses.tests.test_homework_scoring_view_warnings`.
- [x] Split Datamailer recipient-list audit command tests into shared fixture,
  command, member-response, and repair-assertion helpers plus focused no-drift,
  repair, listing-error, and option-validation scenario classes. Verification:
  `uv run ruff check courses/tests/test_datamailer_recipient_list_audit.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_list_audit`.
- [x] Split the shared dashboard homework stats test base into focused
  dashboard fixture, submission-stat, formatted-time, and difficulty mixins
  while keeping the public base class stable. Verification:
  `uv run ruff check courses/tests/dashboard_homework_base.py courses/tests/test_dashboard_homework_stats.py courses/tests/test_dashboard_homework_difficulty.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_dashboard_homework_stats courses.tests.test_dashboard_homework_difficulty`.
- [x] Split Datamailer recipient-list sync command tests into focused bulk
  upsert, project-passed reconcile, graduate, dry-run, and option-validation
  scenario classes. Also reused the shared registration fixture instead of
  local dry-run model setup. Verification:
  `uv run ruff check courses/tests/test_datamailer_recipient_lists.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_lists`.
- [x] Split the shared project statistics test base into focused fixture,
  submission, model-stat, raw-stat, and incomplete-project mixins while keeping
  the public base class stable. Verification:
  `uv run ruff check courses/tests/project_statistics_base.py courses/tests/test_project_statistics.py courses/tests/test_project_statistics_model.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_statistics courses.tests.test_project_statistics_model`.
- [x] Split Datamailer registration tests into shared fixture, confirmation
  assertion, and membership assertion mixins plus focused confirmation payload,
  confirmation send, membership sync, and membership removal scenario classes.
  Verification:
  `uv run ruff check courses/tests/test_datamailer_registration.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_registration`.
- [x] Split the shared Datamailer project score test base into focused fixture,
  score-payload assertion, project-score scenario fixture, and list-send
  assertion mixins while keeping the public base class stable. Verification:
  `uv run ruff check courses/tests/datamailer_project_score_base.py courses/tests/test_datamailer_project_scores.py courses/tests/test_datamailer_project_outcomes.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_project_scores courses.tests.test_datamailer_project_outcomes`.
- [x] Split the shared cadmin project view test base into focused fixture,
  submission fixture, submission-list fixture, edit fixture, URL, and
  submission-assertion mixins while keeping the public base class stable.
  Verification:
  `uv run ruff check cadmin/tests/project_view_base.py cadmin/tests/test_project_views.py cadmin/tests/test_project_submission_edit_views.py cadmin/tests/test_project_action_views.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_project_views cadmin.tests.test_project_submission_edit_views cadmin.tests.test_project_action_views`.
- [x] Split the shared enrollment data API test base into focused course,
  user, project, URL, certificate request, and certificate assertion mixins
  while keeping the public base class stable. Verification:
  `uv run ruff check data/tests/enrollment_base.py data/tests/test_enrollment.py data/tests/enrollment_passed_base.py data/tests/test_enrollment_passed.py data/tests/test_enrollment_certificates.py data/tests/test_enrollment_certificate_notifications.py docs/refactoring-plan.md`,
  `uv run python manage.py test data.tests.test_enrollment data.tests.test_enrollment_passed data.tests.test_enrollment_certificates data.tests.test_enrollment_certificate_notifications`.
- [x] Split peer-review badge end-to-end tests into focused fixture,
  assignment, review-submission, badge-state assertion, and scoring mixins while
  keeping the concrete progression test focused on the scenario flow.
  Verification:
  `uv run ruff check courses/tests/test_peer_review_badge.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_peer_review_badge`.
- [x] 2026-07-02: Split project-evaluation submit tests into focused auth,
  GET-context, POST-persistence, and voting test cases while keeping shared
  fixtures in the existing project-evaluation base. Verification:
  `uv run ruff check courses/tests/test_project_eval.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_eval`.
- [x] 2026-07-02: Split course project-submission list tests into focused
  fixture, request, pagination, assertion, page, link, and display classes so
  the scenario tests stay small. Verification:
  `uv run ruff check courses/tests/test_course_project_submissions.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_course_project_submissions`.
- [x] 2026-07-02: Split Datamailer certificate tests into focused fixture,
  certificate-availability assertion, course-graduate assertion, payload, and
  send-flow test classes. Verification:
  `uv run ruff check courses/tests/test_datamailer_certificates.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_certificates`.
- [x] 2026-07-02: Split homework submission-confirmation helper mixin into
  direct post-data, payload-assertion, field-expectation, and answer-
  expectation mixins, and updated the integration test to import them directly
  without a compatibility umbrella. Verification:
  `uv run ruff check courses/tests/homework_submission_confirmation_helpers.py courses/tests/test_homework_submission_integrations.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_homework_submission_integrations`.
- [x] 2026-07-02: Split cadmin view-model tests into shared fixture/assertion
  mixins plus focused project-submission and enrollment status-filter scenario
  classes. Verification:
  `uv run ruff check cadmin/tests/test_view_models.py docs/refactoring-plan.md`,
  `uv run python manage.py test cadmin.tests.test_view_models`.
- [x] 2026-07-02: Split the shared Datamailer membership test base into
  fixture, outcome-fixture, upsert-assertion, and removal-assertion mixins while
  keeping the existing public base class stable for current test modules.
  Verification:
  `uv run ruff check courses/tests/datamailer_membership_base.py courses/tests/test_datamailer_membership.py courses/tests/test_datamailer_membership_outcomes.py courses/tests/test_datamailer_membership_removals.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_membership courses.tests.test_datamailer_membership_outcomes courses.tests.test_datamailer_membership_removals`.
- [x] 2026-07-02: Split project voting tests into fixture/base helpers plus
  focused page, action, vote-limit, and all-submissions display test cases.
  Verification:
  `uv run ruff check courses/tests/test_project_voting.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_voting`.
- [x] 2026-07-02: Split the shared project assignment test base into
  submission fixture, assignment assertion, URL, and optional-evaluation mixins
  while keeping the existing base class stable for assignment and optional
  evaluation tests. Verification:
  `uv run ruff check courses/tests/project_assign_base.py courses/tests/test_project_assign.py courses/tests/test_project_optional_eval.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_project_assign courses.tests.test_project_optional_eval`.
- [x] 2026-07-02: Split Datamailer status command output rendering into a
  dedicated status-output module so the management command only coordinates
  arguments, configuration checks, and Datamailer lookups. Verification:
  `uv run ruff check courses/management/commands/datamailer_status.py course_management/datamailer/status_output.py courses/tests/test_datamailer_status.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_status`.
- [x] 2026-07-02: Split the shared Datamailer homework-score test base into
  fixture, payload-assertion, scored-submission fixture, and send-assertion
  mixins while keeping the existing base class stable for payload and send
  tests. Verification:
  `uv run ruff check courses/tests/datamailer_homework_score_base.py courses/tests/test_datamailer_homework_scores.py courses/tests/test_datamailer_homework_score_send.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_homework_scores courses.tests.test_datamailer_homework_score_send`.
- [x] 2026-07-02: Split Datamailer campaign command parser groups and response
  output helpers out of the command class as module-level functions, keeping
  command handling focused on validation, configuration, and execution.
  Verification:
  `uv run ruff check courses/management/commands/datamailer_campaign.py courses/tests/test_datamailer_campaign_command.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_campaign_command`.
- [x] 2026-07-02: Split Datamailer recipient-list sync command parser groups,
  batch output, and sync assembly out of the command class as module-level
  functions, leaving the command class focused on option validation and
  orchestration. Verification:
  `uv run ruff check courses/management/commands/sync_datamailer_recipient_lists.py courses/tests/test_datamailer_recipient_lists.py courses/tests/test_datamailer_recipient_list_imports.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_recipient_list_imports`.
- [x] 2026-07-02: Split Datamailer contact sync batching, dry-run output,
  import payload construction, sync execution, and result formatting out of the
  command class as module-level functions. Verification:
  `uv run ruff check courses/management/commands/sync_datamailer_contacts.py courses/tests/test_datamailer_contact_backfill.py docs/refactoring-plan.md`,
  `uv run python manage.py test courses.tests.test_datamailer_contact_backfill`.
- [x] 2026-07-02: Tightened the test cleanup rule so long focused test classes
  remain acceptable, and test inheritance, base classes, and mixins are not
  introduced just to reduce line counts.
- [x] 2026-07-02: Replaced Datamailer client mixins with concrete endpoint
  clients owned by `DatamailerClient.contacts`,
  `DatamailerClient.recipient_lists`, `DatamailerClient.transactional`, and
  `DatamailerClient.campaigns`; updated production callers and mocks to use
  those endpoint clients directly. Verification:
  `uv run python manage.py test courses.tests.test_datamailer_client courses.tests.test_datamailer_contact courses.tests.test_datamailer_contact_backfill courses.tests.test_datamailer_membership courses.tests.test_datamailer_membership_outcomes courses.tests.test_datamailer_membership_removals courses.tests.test_datamailer_outbox_contacts courses.tests.test_datamailer_outbox_memberships courses.tests.test_datamailer_outbox_status_commands courses.tests.test_datamailer_preferences courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_recipient_list_imports courses.tests.test_datamailer_recipient_list_audit courses.tests.test_datamailer_sync_status courses.tests.test_datamailer_transactional courses.tests.test_datamailer_campaign_command courses.tests.test_datamailer_certificates courses.tests.test_datamailer_registration courses.tests.test_datamailer_peer_review courses.tests.test_datamailer_project_outcomes courses.tests.test_datamailer_homework_score_send courses.tests.test_deadline_reminder_dry_run courses.tests.test_deadline_reminder_homework courses.tests.test_deadline_reminder_peer_review courses.tests.test_deadline_reminder_project cadmin.tests.test_campaign_datamailer_views`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), and
  `git diff --check`.
- [x] 2026-07-02: Split `DatamailerClient.recipient_lists` into member,
  import, and send endpoint clients so the former recipient-list client no
  longer carries unrelated endpoint groups in one large class. Production
  callers now use `client.recipient_lists.members`,
  `client.recipient_lists.imports`, and `client.recipient_lists.sends`
  directly, without forwarding methods. Verification:
  `uv run python manage.py test courses.tests.test_datamailer_client courses.tests.test_datamailer_recipient_lists courses.tests.test_datamailer_recipient_list_imports courses.tests.test_datamailer_recipient_list_audit courses.tests.test_datamailer_membership courses.tests.test_datamailer_membership_outcomes courses.tests.test_datamailer_membership_removals courses.tests.test_datamailer_outbox_memberships courses.tests.test_datamailer_outbox_status_commands courses.tests.test_datamailer_certificates courses.tests.test_datamailer_peer_review courses.tests.test_datamailer_project_outcomes courses.tests.test_datamailer_homework_score_send courses.tests.test_datamailer_registration courses.tests.test_deadline_reminder_dry_run courses.tests.test_deadline_reminder_homework courses.tests.test_deadline_reminder_peer_review courses.tests.test_deadline_reminder_project`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), production large-class
  scan now reports only `CourseRegistrationForm`, and `git diff --check`.
- [x] 2026-07-02: Moved course-registration form field setup,
  authenticated-user setup, email normalization, duplicate lookup, and profile
  save support into module helpers so `CourseRegistrationForm` keeps only the
  Django form hooks and save orchestration. Verification:
  `uv run python manage.py test courses.tests.test_registration_campaigns courses.tests.test_registration_campaign_notifications courses.tests.test_registration_campaign_course_page api.tests.test_registration_campaigns api.tests.test_registration_campaign_auth`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), production large-class
  scan reports `production_large_classes=0`, and `git diff --check`.
- [x] 2026-07-02: Removed the trivial
  `DatamailerRecipientListCommandMixin` from recipient-list command tests and
  replaced it with a module helper, leaving the concrete tests with only their
  real command-test base. Verification:
  `uv run python manage.py test courses.tests.test_datamailer_recipient_lists`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), and
  `git diff --check`.
- [x] 2026-07-02: Collapsed the local cadmin view-model fixture/assertion
  mixins into the focused `CadminViewModelBase`, removing an inheritance layer
  without splitting the coherent test setup. Verification:
  `uv run python manage.py test cadmin.tests.test_view_models`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), and
  `git diff --check`.
- [x] 2026-07-02: Removed local cadmin Datamailer view-test mixins by moving
  operations helpers into the operations test, requeue helpers into the
  requeue test, and contact-event creation into a module helper. Verification:
  `uv run python manage.py test cadmin.tests.test_datamailer_views`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), and
  `git diff --check`.
- [x] 2026-07-02: Removed local Datamailer certificate test mixins by moving
  certificate fixtures and payload assertions to module helpers, leaving both
  concrete test classes as direct `TestCase` subclasses. Verification:
  `uv run python manage.py test courses.tests.test_datamailer_certificates`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), and
  `git diff --check`.
- [x] 2026-07-02: Removed local Datamailer registration test mixins by moving
  registration fixtures, confirmation assertions, and membership assertions to
  module helpers, leaving concrete registration tests as direct `TestCase`
  subclasses. Verification:
  `uv run python manage.py test courses.tests.test_datamailer_registration`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), and
  `git diff --check`.
- [x] 2026-07-02: Removed local Datamailer peer-review notification test
  mixins by moving assignment fixtures, payload assertions, and send-audit
  assertions to module helpers, leaving concrete peer-review tests as direct
  `TestCase` subclasses. Verification:
  `uv run python manage.py test courses.tests.test_datamailer_peer_review`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), and
  `git diff --check`.
- [x] 2026-07-02: Removed local project-voting test mixins by folding the
  shared fixture helpers into the focused voting base and moving extra
  submission helpers into the only test class that uses them. Verification:
  `uv run python manage.py test courses.tests.test_project_voting`,
  `uvx pyrefly check`, repository AST cleanup scan
  (`forbidden_comprehensions=0`, `threshold_violations=0`,
  `append_constructed=0`, `wide_tuple_unpacking=0`,
  `wide_positional_calls=0`, `wide_function_args=0`), and
  `git diff --check`.
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
- [ ] Audit test-helper inheritance introduced during earlier cleanup and
  collapse it when the base class or mixin layer is only serving line-count
  reduction. Keep long focused test classes intact when their setup and subject
  are coherent.
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
