run:
	pipenv run python manage.py runserver 0.0.0.0:8000


migrations:
	pipenv run python manage.py makemigrations
	pipenv run python manage.py migrate


tests:
	pipenv run python manage.py test courses.tests


data:
	pipenv run python add_data.py


shell:
	pipenv run python manage.py shell


admin:
	pipenv run python manage.py createsuperuser