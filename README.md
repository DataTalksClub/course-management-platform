# Course Management System

A Django-based web application for managing and participating in
DataTalks.Club courses.

The platform supports course administration, homework and project
submissions, peer review workflows, course leaderboards, and API access
to course data.

## Features

- User authentication: registration and login for students and instructors.
- Course management: instructors can create and manage courses.
- Homework and projects: students can submit homework and projects.
- Peer reviews: students can evaluate project submissions from their peers.
- Leaderboard: course rankings based on submitted work and scores.
- API access: authenticated endpoints for course, homework, project, graduate,
  certificate, and OpenAPI data.
- Health check: a public endpoint for service monitoring.

## Project Structure

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
7. Ask for the local OAuth keys. Do not share them publicly.
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
