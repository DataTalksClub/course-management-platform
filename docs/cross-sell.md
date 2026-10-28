# Cross-sell after registration

After someone registers on a campaign page (`/register/<slug>/`), the
success panel suggests up to three other courses. The confirmation email
lists the same suggestions.

Code: `courses/cross_sell.py`. Template: `courses/templates/courses/_cross_sell.html`.

## Relevance rule

The rule is deterministic, and `suggestions(source_campaign, user, email)` implements it:

1. Candidates are active registration campaigns that are:
   - not flagged `exclude_from_suggestions`;
   - not listed in `CROSS_SELL_EXCLUDED_CAMPAIGNS`;
   - not the source campaign, and not another form for the same edition;
   - for a course edition that is not `finished`. Campaigns with no edition yet ("next cohort") are included.
2. Campaigns the person is already registered for (same user or normalized
   email) are dropped. So are campaigns whose edition the person is
   enrolled in.
3. The source campaign's curated **Suggested courses** come first. All
   other open campaigns follow as a fallback, so an uncurated course still
   gets suggestions. Each group is sorted by edition start date (soonest
   first, undated last), then by slug.
4. The first `CROSS_SELL_MAX_SUGGESTIONS` (default 3) are shown.

## Configuration

- **Per course:** on the campaign edit page (cadmin or Django admin), the
  "Cross-sell" section has a **Suggested courses** list (curated, ordered by
  start date) and **Never suggest this form**.
- **Settings:**
  - `CROSS_SELL_MAX_SUGGESTIONS` (env, default `3`).
  - `CROSS_SELL_EXCLUDED_CAMPAIGNS` (env, comma-separated campaign slugs that are never suggested).

## One-click registration

Each suggestion has a **Register** button, and a checkbox list registers
several at once (`POST /register/<slug>/also/`). The new registrations copy
these fields from the visitor's registration on the source campaign:

- name
- email
- company
- country/region
- role
- years of experience
- newsletter consent

Nobody re-enters anything. The source registration is found from the
logged-in account, or from the anonymous session that just submitted the
form. Course-specific consent (Nebius sharing) and application answers are
never copied.

- **Application-only courses:** campaigns for courses with
  `requires_registration_approval` are never registered in one click. They
  show an **Apply** link to their own form.
- **Allowed slugs:** only slugs from the current suggestion set are
  accepted. Anything else is ignored.
- **Double submits:** these are idempotent, because of the unique
  campaign + email constraint.
- **Email confirmation:** copies send no confirmation email of their own.
  - If the source is already confirmed, the copy is created confirmed (same address).
  - If not, it is confirmed together with the source when the confirmation link is clicked.
  - Copies never get reminders and are deleted with the source (`referred_by` cascades) when it is cleaned up unconfirmed.
  - Fixing the source email drops unconfirmed copies.

## Confirmation email

The confirmation payload context has:

- `suggested_courses`: a list of `{title, start_date, url}`.
- `suggested_courses_text`: the same list as plain text.

The text is also appended to `next_steps_text`, which the Relay
`registration-confirmation` template already renders, so no Relay template
change is needed. A template can use `suggested_courses` for richer markup.
Email links carry `?src=xsell-email&from=<source slug>`.

## Tracking and conversion

`CourseRegistration.source` and `CourseRegistration.referred_by` record
where a registration came from:

| `source`      | Meaning                                                        |
|---------------|----------------------------------------------------------------|
| (empty)       | Normal form registration                                       |
| `xsell`       | One-click registration from the success page                   |
| `xsell-link`  | Followed a suggestion link (e.g. Apply/Details), then the form |
| `xsell-email` | Followed a suggestion link in the confirmation email           |

Events go through `record_event` (no PII, only slugs and ids):

- `cross_sell.impression`: the success panel showed suggestions
  (`from_campaign_slug`, `suggested_campaign_slugs`).
- `cross_sell.click`: a campaign page was opened from a suggestion link
  (`from_campaign_slug`, `campaign_slug`, `source`).
- `cross_sell.registered`: a registration was created from a suggestion
  (`from_campaign_slug`, `campaign_slug`, `registration_id`,
  `referred_by_id`, `source`).

Conversion is `cross_sell.registered` divided by `cross_sell.impression`.
Admin → Course registrations can be filtered by `source`.
