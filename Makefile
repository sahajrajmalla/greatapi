.DEFAULT_GOAL := help
VENV     ?= .venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/python -m pip
# uv is used when present purely because it is faster; plain pip works identically.
INSTALLER := $(shell command -v uv 2>/dev/null)

.PHONY: help
help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV):
	python3 -m venv $(VENV)

.PHONY: install
install: $(VENV)  ## Create the venv and install everything for development
ifneq ($(INSTALLER),)
	uv pip install --python $(PY) -e ".[dev,docs]"
else
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev,docs]"
endif
	$(VENV)/bin/pre-commit install
	@echo "\nReady. Run 'make demo' to see it work, or 'make check' before you push."

.PHONY: install-base
install-base: $(VENV)  ## Reinstall with NO optional extras (for extras-isolation testing)
ifneq ($(INSTALLER),)
	uv pip install --python $(PY) --reinstall -e "." pytest pytest-asyncio pytest-cov httpx
else
	$(PIP) install --force-reinstall -e "." pytest pytest-asyncio pytest-cov httpx
endif

.PHONY: lint
lint:  ## Ruff lint + format check, then strict mypy
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/ruff format --check src tests
	$(VENV)/bin/mypy

.PHONY: format
format:  ## Autofix lint issues and format
	$(VENV)/bin/ruff check --fix src tests
	$(VENV)/bin/ruff format src tests

.PHONY: test
test:  ## Run the full suite with coverage
	$(VENV)/bin/pytest --cov=greatapi --cov-report=term-missing --cov-fail-under=85

.PHONY: test-base
test-base:  ## Prove the core works with zero optional dependencies installed
	$(VENV)/bin/pytest -m "not requires_ai" --no-cov

.PHONY: check
check: lint test  ## Everything CI runs on a pull request

.PHONY: build
build:  ## Build the sdist + wheel and validate the metadata
	rm -rf dist
	$(PY) -m build
	$(VENV)/bin/twine check dist/*

.PHONY: demo
demo:  ## Run the example app (streaming chat + agent + admin, no API key needed)
	cd examples/chat && ../../$(PY) -m greatapi.cli runserver --reload

.PHONY: docs
docs:  ## Serve the documentation site on :8001
	$(VENV)/bin/mkdocs serve -a localhost:8001

.PHONY: clean
clean:  ## Remove build artefacts and caches
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
