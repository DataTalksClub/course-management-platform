# Course Management System

A Django-based web application designed for managing and
participating in DataTalks.Club courses. This platform allows
instructors to create and manage courses, assignments, and
peer reviews.

Students can enroll in courses, submit homework, projects
and engage in peer evaluations.

## Features

- **User Authentication**: Registration and login functionality for students and instructors.
- **Course Management**: Instructors can create and manage courses.
- **Homework and Projects**: Students can submit homework and projects; instructors can manage assignments.
- **Peer Reviews**: Facilitates peer review process for project evaluations.
- **Leaderboard**: Displays student rankings based on performance in courses.


## Project Structure

```
├── accounts/ # Handles user accounts and authentication
├── course_management/ # Main project folder with settings and root configurations
├── courses/ # Main logic is here (courses, homeworks, etc)
├── templates/ # Global templates directory for the project
```

## Running it locally

### Installing dependencies

This project uses uv for dependency management and requires Python 3.13.

Install uv if you don't have it yet:

```bash
pip install uv
```

Install Python 3.13 and dependencies:

```bash
uv python install 3.13
uv sync --dev
```

### Prepare the service

Set the database to local:

```bash
export DATABASE_URL="sqlite:///db/db.sqlite3"
```

Make migrations:

```bash
make migrations
# uv run python manage.py migrate
```

Add an admin user:

```bash
make admin
# uv run python manage.py createsuperuser
```

Add some data:

```bash
make data
```

### Running the service

```bash
make run
# uv run python manage.py runserver 0.0.0.0:8000
```

## Running with Docker

Build it:

```bash
docker build -t course_management .
```

Run it:

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

remove the container later

```bash
docker rm course_management
```

get to the container

```bash
docker exec -it course_management bash
```

## Getting the data

There are `/data` endpoints for getting the data

Using them:

```bash
TOKEN="TEST_TOKEN"
HOST="http://localhost:8000"
COURSE="fake-course"
HOMEWORK="hw1"

curl \
    -H "Authorization: ${TOKEN}" \
    "${HOST}/data/${COURSE}/homework/${HOMEWORK}"
```

Make sure to run `make data` to create the admin user and 
data (including authentication token)


## Authentication setup

If you want to authenticate with OAuth locally
(not requeired for testing), do the following

* Go to the admin panel (http://localhost:8000/admin)
* Add a record to "Sites"
    * "localhost:8000" for display and domain names
    * note the ID of the site (probably it's "2")
* Add records to "Social applications":
    * GoogleDTC. Provider: Google
    * Ask Alexey for the keys. Don't share them publicly
    * For the site, choose the localhost one

Export `SITE_ID` (should be the ID of the localhost site):

```bash
export SITE_ID=2
```

Restart the app:

```bash
python manage.py runserver 0.0.0.0:8000
```

Now log out as admin and log in with Google



## DB connection

Prep work

```
Host bastion-tunnel
    HostName <IP>
    User ubuntu
    IdentityFile c:/Users/alexe/.ssh/<KEY>.pem
    LocalForward 5433 dev-course-management-cluster.cluster-cpj5uw8ck6vb.eu-west-1.rds.amazonaws.com:5432
    ServerAliveInterval 60
```

Connect to the bastion

```bash
ssh bastion-tunnel
```

And then

```bash
pgcli -h localhost -p 5433 -u pgusr -d coursemanagement
```

When connecting for the first time, create dev and prod schemas

```SQL
CREATE DATABASE dev;
CREATE DATABASE prod;
```

Django shell

```bash
export DATABASE_URL="postgresql://pgusr:${DB_PASSWORD}@localhost:5433/dev"
export SECRET_KEY="${DJANGO_SECRET}"

pipenv run python manage.py shell
```

or

```bash
export DATABASE_URL="postgresql://pgusr:${DB_PASSWORD}@localhost:5433/prod"
export SECRET_KEY="${DJANGO_SECRET}"
```

Finding user with email:

```python
from django.contrib.auth import get_user_model
User = get_user_model()

user = User.objects.get(email='test@gmail.com')
```


