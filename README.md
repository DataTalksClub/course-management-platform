# Course Management System

A Django-based web application for managing and participating in
DataTalks.Club courses.

The platform supports course administration, homework and project
submissions, peer review workflows, and course leaderboards. It also
provides API access to course data.

## Features

The main features are:

- User authentication: registration and login.
- Course management: instructors can create and manage courses.
- Homework and projects: students can submit homework and projects.
- Peer reviews: students can evaluate project submissions from their peers.
- Leaderboard: course rankings based on submitted work and scores.
- API access: authenticated endpoints for course, homework, project, graduate,
  certificate, and OpenAPI data.
- Health check: a public endpoint for service monitoring.

## Project Structure

The main directories are:

```text
├── accounts/             # User accounts and authentication
├── api/                  # OpenAPI schema and API tests
├── cadmin/               # Custom admin views
├── course_management/    # Django project settings and root configuration
├── courses/              # Course, homework, project, and review logic
├── data/                 # Public and authenticated data API views
├── deploy/               # Deployment scripts
├── docs/                 # Project documentation
├── notebooks/            # Analysis notebooks
├── templates/            # Shared Django templates
```

## Requirements

Install these tools before running the app:

- Python 3.13
- uv
- Docker and Docker Compose, for containerized local development

Install uv with the official installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Python 3.13 and project dependencies:

```bash
uv python install 3.13
uv sync --dev
```

## Running Locally

Use SQLite for local development:

```bash
export DATABASE_URL="sqlite:///db/db.sqlite3"
```

Prepare the database:

```bash
make migrations
```

Create an admin user:

```bash
make admin
```

Load sample data:

```bash
make data
```

Run the development server:

```bash
make run
```

The app will be available at:

```text
http://localhost:8000
```

Useful direct Django commands:

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver 0.0.0.0:8000
```

## Tests

Run the Django test suite:

```bash
make tests
```

Direct command:

```bash
uv run python manage.py test --timing --durations 30
```

One-time scripts and temporary debug files should go in `.tmp/`, which is
ignored by git.

## Running with Docker

Start the app and PostgreSQL with Docker Compose:

```bash
docker-compose up --build
```

Compose starts:

- `web`: the Django application on port 8000
- `db`: PostgreSQL 17
- `ngrok`: optional TCP tunnel for the database

The app will be available at:

```text
http://localhost:8000
```

Build and run the application image without Compose:

```bash
docker build -t course_management .
```

Then run the image:

```bash
DBDIR=`cygpath -w ${PWD}/db`

docker run -it --rm \
    -p 8000:80 \
    --name course_management \
    -e DATABASE_URL="sqlite:////data/db.sqlite3" \
    -e SITE_ID="${SITE_ID}" \
    -v ${DBDIR}:/data \
    course_management
```

Open a shell in the running container:

```bash
docker exec -it course_management bash
```

## Health Check

The public health check endpoint returns service status and version:

```text
GET /api/health/
```

Example:

```bash
curl http://localhost:8000/api/health/
```

Response:

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

In local development, the version comes from the `VERSION` environment
variable and falls back to `local-development-build-version-not-configured`.

## Relay

The platform syncs users and course enrollments and sends email through Relay.

Set all required environment variables to enable the integration:

```bash
export RELAY_URL="https://relay.dtcdev.click"
export RELAY_API_KEY="<token>"
export RELAY_CLIENT="dtc-courses"
export RELAY_AUDIENCE="dtc-courses"
export RELAY_FROM_EMAIL="courses"
```

Optional settings:

```bash
export RELAY_STRICT="0"
export RELAY_SYNC_ON_USER_CREATE="1"
```

With `RELAY_STRICT=0`, Relay API failures are logged and don't
break signup or enrollment flows. Set `RELAY_STRICT=1` only when those
flows should fail on Relay errors.

`PUBLIC_BASE_URL` is used for links in delivered transactional email. Set it
when sending email from a local server so messages contain public HTTPS links
instead of `localhost` links.

```bash
export PUBLIC_BASE_URL="https://dev.courses.datatalks.club"
```

## Non-delivering email verification (dry run)

To exercise the transactional email path without delivering anything, set
`RELAY_TRANSACTIONAL_DRY_RUN=1`. CMP then adds Relay's `dry_run` flag
to every `POST /api/transactional/send`: the identical prod pipeline runs
(outbox -> dispatch -> send -> `DatamailerSendAudit`), but Relay renders
the email and returns it inline without sending, queuing, or persisting
anything. `DatamailerSendAudit` is retained as a historical database model name;
it does not select or configure the old service.

The rendered subject/bodies land in the audit's `response_payload["rendered"]`,
which CMP exposes over HTTP at `GET /api/datamailer/send-audits`
(filter by `email` / `template_key` / `idempotency_key`). The e2e smoke suite
uses this to verify confirmation emails safely.

Deadline reminder emails are triggered by a short CMP management command:

```bash
uv run python manage.py send_deadline_reminders
```

For deployed environments, this command is run on a schedule as a one-off ECS
task. The recurring trigger (an EventBridge/CloudWatch rule targeting
`ecs:RunTask` with the `send_deadline_reminders` command override) and its
invocation role are provisioned via Terraform in `DataTalksClub/infra-terraform`,
alongside the CMP ECS service. CMP doesn't configure the schedule.

The scheduled task exits after reconciling Relay recipient lists and
triggering Relay list sends. Relay handles per-recipient delivery
asynchronously.

Every event is attempted even if an earlier one fails; each failure is written
to stderr and recorded on the `DatamailerSendAudit` row, and the command exits
non-zero at the end if any event failed. To see why a reminder never arrived:

```bash
curl -s -H "Authorization: Token $TOKEN" \
  "https://courses.datatalks.club/api/datamailer/send-audits?template_key=deadline-reminder"
```

Bulk sends post the whole recipient list inline, so they use a longer HTTP
timeout than transactional sends (`RELAY_TIMEOUT_SECONDS`, default 60).
Don't lower it: hanging up mid-request makes Relay abandon the dispatch it
is partway through, stranding every not-yet-sent message at `queued` with no
error and no retry, while CMP records a failure for work that partly succeeded.

Relay transactional template keys are stable code-level constants in CMP.
Don't configure one environment variable per template.

The CMP/Relay integration, including the conceptual design and API reference,
is documented in the historically named
[`docs/datamailer-integration.md`](docs/datamailer-integration.md).

## API Data Access

Most `/api` endpoints require token authentication:

```text
Authorization: Token <token>
```

Example:

```bash
TOKEN="TEST_TOKEN"
HOST="http://localhost:8000"
COURSE="fake-course"
HOMEWORK="hw1"

curl \
    -H "Authorization: Token ${TOKEN}" \
    "${HOST}/api/courses/${COURSE}/homeworks/${HOMEWORK}/submissions"
```

Run `make data` to create sample data, including an authentication token.

See [endpoints.md](./endpoints.md) for API documentation, including:

- OpenAPI specification
- Public course criteria
- Public health check
- Public leaderboard data
- Homework data
- Project data
- Graduate data
- Certificate updates
- Course management API

## Local OAuth Setup

OAuth is optional for local testing.

To configure Google OAuth locally:

1. Go to the admin panel at `http://localhost:8000/admin`.
2. Add a record to `Sites`.
3. Use `localhost:8000` for the display name and domain name.
4. Note the site ID, usually `2`.
5. Add a record to `Social applications`.
6. Use `GoogleDTC` as the name and `Google` as the provider.
7. Ask for the local OAuth keys. Don't share them publicly.
8. Attach the application to the localhost site.

Export the local site ID:

```bash
export SITE_ID=2
```

Restart the app:

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

Then log out as admin and log in with Google.

## Database Tunnel

Example SSH config for an RDS tunnel:

```text
Host bastion-tunnel
    HostName <IP>
    User ubuntu
    IdentityFile c:/Users/alexe/.ssh/<KEY>.pem
    LocalForward 5433 dev-course-management-cluster.cluster-cpj5uw8ck6vb.eu-west-1.rds.amazonaws.com:5432
    ServerAliveInterval 60
```

Connect to the bastion:

```bash
ssh bastion-tunnel
```

Connect to PostgreSQL through the tunnel:

```bash
pgcli -h localhost -p 5433 -u pgusr -d coursemanagement
```

When connecting for the first time, create the dev and prod databases:

```sql
CREATE DATABASE dev;
CREATE DATABASE prod;
```

Open a Django shell against dev:

```bash
export DATABASE_URL="postgresql://pgusr:${DB_PASSWORD}@localhost:5433/dev"
export SECRET_KEY="${DJANGO_SECRET}"
uv run python manage.py shell
```

Open a Django shell against prod:

```bash
export DATABASE_URL="postgresql://pgusr:${DB_PASSWORD}@localhost:5433/prod"
export SECRET_KEY="${DJANGO_SECRET}"
uv run python manage.py shell
```

Find a user by email:

```python
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.get(email="test@gmail.com")
```
