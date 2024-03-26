TAG := $(shell date +"%Y%m%d-%H%M%S")
REPO_ROOT := 387546586013.dkr.ecr.eu-west-1.amazonaws.com
REPO_URI := $(REPO_ROOT)/course-management

SITE_ID ?= 2

run: ## Run django server
run:
	pipenv run python manage.py runserver 0.0.0.0:8000


migrations: ## Make migrations
migrations:
	pipenv run python manage.py makemigrations
	pipenv run python manage.py migrate


admin: ## Add an admin user
admin:
	pipenv run python manage.py createsuperuser


tests: ## Run tests
tests:
	pipenv run python manage.py test courses.tests


data: ## Add data to database
data: migrations
	pipenv run python add_data.py

test_data: data
	pipenv run python add_more_test_data.py

shell: ## Run django shell
shell:
	pipenv run python manage.py shell


tunnel_prod: ## Open tunnel to prod
	bash tunnel-prod.sh

notebook: ## Run a jupyter notebook
notebook:
	pipenv run jupyter notebook


docker_build: ## Build docker image
docker_build: tests
	docker build -t course_management:$(TAG) .


docker_run: ## Run docker container
docker_run: docker_build
	docker run -it --rm \
		-p 8000:80 \
		--name course_management \
		-e SITE_ID="$(SITE_ID)" \
		-e DEBUG="1" \
		-e DATABASE_URL="sqlite:////data/db.sqlite3" \
		-e VERSION=$(TAG) \
		-v `cygpath -w ${PWD}/db`:/data \
		course_management:$(TAG)


docker_bash: ## Run bash in docker container
docker_bash:
	docker exec -it course_management bash


docker_auth: ## Authenticate to ECR
docker_auth:
	aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin $(REPO_ROOT)


docker_publish: ## Publish docker image to ECR
docker_publish: docker_build docker_auth
	docker tag course_management:$(TAG) $(REPO_URI):$(TAG)
	docker push $(REPO_URI):$(TAG)


deploy_dev:		## Deploy to dev environment
deploy_dev: docker_publish
	bash deploy/deploy_dev.sh $(TAG)


deploy_prod: ## Deploy to prod environment
deploy_prod:
	bash deploy/deploy_prod.sh



help:    ## Show this help.
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'