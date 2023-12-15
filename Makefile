run:
	pipenv run python manage.py runserver 0.0.0.0:8000


migrations:
	pipenv run python manage.py makemigrations
	pipenv run python manage.py migrate


data:
	pipenv run python manage.py loaddata initial_data.json
