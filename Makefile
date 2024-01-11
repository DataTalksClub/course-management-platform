localvars:
	export DATABASE_URL="sqlite:///db/db.sqlite3"

run: localvars
	pipenv run python manage.py runserver 0.0.0.0:8000


migrations: localvars
	pipenv run python manage.py makemigrations
	pipenv run python manage.py migrate


tests: localvars
	pipenv run python manage.py test courses.tests


data: localvars
	pipenv run python add_data.py


shell: localvars
	pipenv run python manage.py shell