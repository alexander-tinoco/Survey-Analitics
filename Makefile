.PHONY: help build up down logs shell test lint format migrate superuser clean

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

shell:  ## Open a shell inside the web container
	docker compose run --rm web bash

test:  ## Run the test suite with coverage
	docker compose run --rm web pytest

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
