run:
	pipenv run python manage.py runserver 0.0.0.0:8000


migrations:
	pipenv run python manage.py makemigrations
	pipenv run python manage.py migrate


data:
	pipenv run python add_data.py


admin:
	pipenv run python manage.py createsuperuser