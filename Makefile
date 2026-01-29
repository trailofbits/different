.PHONY: dev lint format test build clean

dev:
	uv sync --all-groups

lint:
	uv run ruff format --check . && uv run ruff check . && uv run ty check src/

format:
	uv run ruff format .

test:
	uv run pytest

test-fast:
	uv run pytest -x -q --no-cov

build:
	uv build

clean:
	rm -rf dist/ build/ *.egg-info/ .pytest_cache/ .coverage htmlcov/
