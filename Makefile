.PHONY: up down build migrate test test-one logs

up:        ## Start API, worker, Postgres, Redis
	docker compose up --build

down:      ## Stop and remove containers
	docker compose down

build:     ## Build images
	docker compose build

migrate:   ## Apply DB migrations inside the api container
	docker compose run --rm api alembic upgrade head

test:      ## Run the test suite
	uv run pytest

test-one:  ## Run a single test: make test-one T=tests/test_x.py::test_y
	uv run pytest $(T)

logs:      ## Tail logs
	docker compose logs -f
