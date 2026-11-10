TAG := $(shell date +"%Y%m%d-%H%M%S")

SITE_ID ?= 2

.PHONY: run migrations admin user tests tests-postgres typecheck data load_rds_export test_data shell notebook docker_build docker_run docker_bash sync help

run: ## Run django server
run:
	uv run python manage.py runserver 0.0.0.0:8000


migrations: ## Make migrations
migrations:
	uv run python manage.py makemigrations
	uv run python manage.py migrate


admin: ## Add an admin user
admin:
	uv run python manage.py createsuperuser


user:
	uv run python -m scripts.add_user


tests: ## Run tests
tests:
	uv run python manage.py test --timing --durations 30

tests-postgres: ## Run all pytest tests and Django checks on disposable PostgreSQL 16
	bash scripts/test_postgres.sh

typecheck: ## Run static type checks
typecheck:
	uv run pyrefly check


data: ## Add data to database
data: migrations
	uv run python -m scripts.add_data

load_rds_export: ## Load latest /tmp/rds-export/rds-prod-*.db into db/db.sqlite3
	uv run python scripts/load_rds_export.py

test_data: data
	uv run python -m scripts.add_more_test_data

shell: ## Run django shell
shell:
	uv run python manage.py shell


notebook: ## Run a jupyter notebook
notebook:
	uv run jupyter notebook


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


sync: ## Install dev dependencies
sync:
	uv sync --dev


help:    ## Show this help.
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'
