.PHONY: help build up down logs worker-logs worker-reload shell test test-engine lint format migrate superuser clean

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build:  ## Build the application image
	docker compose build

up:  ## Start the stack (web, db, redis)
	docker compose up

down:  ## Stop the stack and remove containers
	docker compose down

logs:  ## Tail the web service logs
	docker compose logs -f web

worker-logs:  ## Tail the Celery worker logs
	docker compose logs -f worker

worker-reload:  ## Restart the worker to pick up code changes
	# Celery does not reload code the way runserver does, so a newly added
	# or edited task is invisible until the worker restarts.
	docker compose restart worker

shell:  ## Open a shell inside the web container
	docker compose run --rm web bash

test:  ## Run the test suite with coverage
	docker compose run --rm web pytest

test-engine:  ## Run the analytics engine tests at their 100% gate
	docker compose run --rm web pytest tests/analytics -o addopts="" \
		--cov=apps/analytics/engine --cov-report=term-missing --cov-fail-under=100

lint:  ## Check formatting and lint rules
	docker compose run --rm web ruff check .
	docker compose run --rm web ruff format --check .

format:  ## Apply formatting and fix what can be fixed
	docker compose run --rm web ruff check --fix .
	docker compose run --rm web ruff format .

migrate:  ## Apply database migrations
	docker compose run --rm web python manage.py migrate

superuser:  ## Create an admin user
	docker compose run --rm web python manage.py createsuperuser

clean:  ## Stop the stack and delete volumes (destroys the database)
	docker compose down -v
