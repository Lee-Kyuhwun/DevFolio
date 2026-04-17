.PHONY: dev test lint format clean all

dev:
	pip install -e ".[dev]"

test:
	pytest --cov=devfolio --cov-report=term-missing

lint:
	ruff check devfolio/ tests/

format:
	ruff format devfolio/ tests/

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +

all: lint test
