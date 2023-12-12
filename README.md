# Course Management Platform

A platform for hosting our courses

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
