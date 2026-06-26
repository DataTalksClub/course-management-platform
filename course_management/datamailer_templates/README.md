# CMP transactional email templates

These are the email templates CMP sends through Datamailer. **CMP owns this
content** — Datamailer is client-agnostic and just stores/renders whatever we
push to it over its generic template API. Nothing CMP-specific lives in the
Datamailer repo.

- `definitions.py` — the `TEMPLATES` dict (subject, html/text bodies, required
  context, example context). Each entry's `description` records **which CMP
  process triggers it**.

## If you change a template here, publish it

```bash
uv run python manage.py upsert_datamailer_templates                      # all
uv run python manage.py upsert_datamailer_templates --template-key peer-review-assignment
```

This `PUT`s each template to Datamailer (`/api/transactional/templates/{key}`)
using the `DATAMAILER_*` settings. View them at `<DATAMAILER_URL>/templates/`.

## What triggers each template

| Key | Triggered by |
| --- | --- |
| `homework-submission-confirmation` | Learner submits/updates a homework |
| `project-submission-confirmation` | Learner submits/updates a project |
| `homework-score-notification` | Staff score the homework (cadmin → Score homework) |
| `project-score-notification` | Staff score the project (cadmin → Score project) |
| `peer-review-assignment` | Staff assign peer reviews (cadmin → Assign peer reviews) |
| `certificate-availability-notification` | A certificate is generated for an enrollment |
| `deadline-reminder` | Scheduled `send_deadline_reminders` job, 24h before a deadline |
