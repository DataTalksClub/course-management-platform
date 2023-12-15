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
├── courses/ # Manages course creation and information
├── homework/ # Handles homework assignments and submissions
├── leaderboard/ # Manages and displays user performance leaderboards
├── main/ # The main app for handling core functionalities
├── peer_reviews/ # Manages peer review functionalities
├── projects/ # Handles project submissions and evaluations
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

Make migrations:

```bash
python manage.py migrate
```

Add an admin user:

```bash
python manage.py createsuperuser
```

### Running the service

```bash
python manage.py runserver 0.0.0.0:8000
```

or 

```bash
make run
```


### Authentication setup

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
