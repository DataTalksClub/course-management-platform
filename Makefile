TAG := $(shell date +"%Y%m%d-%H%M%S")
REPO_ROOT := 387546586013.dkr.ecr.eu-west-1.amazonaws.com
REPO_URI := $(REPO_ROOT)/course-management

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

docker_build:
	docker build -t course_management:$(TAG) .

docker_run: docker_build
	docker run -it --rm \
		-p 8000:80 \
		--name course_management \
		-e DEBUG="0" \
		-e DATABASE_URL="sqlite:////data/db.sqlite3" \
		-v `cygpath -w ${PWD}/db`:/data \
		course_management:$(TAG)


docker_bash:
	docker exec -it course_management bash


docker_publish: docker_build
	docker tag course_management:$(TAG) $(REPO_URI):$(TAG)
	docker push $(REPO_URI):$(TAG)

docker_auth:
	aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin $(REPO_ROOT)