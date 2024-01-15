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

Install pipenv if you don't have it yet:

```bash
pip install pipenv
```

Install the dependencies (you need Python 3.9):

```bash
pipenv install
```

Activate virtual env:

```bash
pipenv shell
```

### Prepare the service

Set the database to local:

```bash
export DATABASE_URL="sqlite:///db.sqlite3"
```

Make migrations:

```bash
make migrations
# python manage.py migrate
```

Add an admin user:

```bash
make admin
# python manage.py createsuperuser
```

Add some data:

```bash
make data
```

### Running the service

```bash
make run
# python manage.py runserver 0.0.0.0:8000
```

## Running with Docker

Build it:

```bash
docker build -t course_management .
```

Run it:

```bash
docker run -d \
    -p 8000:8000 \
    --name course_management \
    -e DATABASE_URL="sqlite:////data/db.sqlite3" \
    -v ${PWD}/db:/data \
    course_management
```

if you're on cygwin:

```bash
docker run -it --rm \
    -p 8000:8000 \
    --name course_management \
    -e DATABASE_URL="sqlite:////data/db.sqlite3" \
    -v `cygpath -w ${PWD}/db`:/data \
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


