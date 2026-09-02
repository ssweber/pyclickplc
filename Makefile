# Makefile for easy development workflows.
# See development.md for docs.
# Note GitHub Actions call uv directly, not this Makefile.

.DEFAULT_GOAL := default

.PHONY: default install lint test upgrade build clean docs-clean docs-generated-clean docs-generate docs-serve docs-build docs-check

default: install lint test

install:
	uv sync --locked --all-extras --dev

lint:
	uv run devtools/lint.py

test:
	uv run pytest

upgrade:
	uv lock --upgrade
	uv sync --locked --all-extras --dev

build:
	uv build

# Improved Windows detection
ifeq ($(OS),Windows_NT)
    WINDOWS := 1
else
    ifeq ($(shell uname -s),Windows)
        WINDOWS := 1
    else
        WINDOWS := 0
    endif
endif

ifeq ($(WINDOWS),1)
	# Windows commands
	RM = powershell -Command "Remove-Item -Recurse -Force"
	RM_SITE = powershell -Command "if (Test-Path 'site') { Remove-Item -Recurse -Force 'site' }"
	FIND_PYCACHE = powershell -Command "Get-ChildItem -Path . -Filter '__pycache__' -Recurse -Directory | Remove-Item -Recurse -Force"
	RM_GENERATED_DOCS = powershell -Command "if (Test-Path 'docs_build') { Remove-Item -Recurse -Force 'docs_build' }"
else
    # Unix commands
    RM = rm -rf
    RM_SITE = rm -rf site/
    FIND_PYCACHE = find . -type d -name "__pycache__" -exec rm -rf {} +
    RM_GENERATED_DOCS = rm -rf docs_build/
endif

docs-generate:
	uv run --group docs python devtools/prepare_docs.py
	uv run --group docs python docs/gen_reference.py --output-dir docs_build
	uv run --group docs python docs/gen_llms.py --docs-dir docs_build --output-file docs_build/llms.txt

docs-serve: docs-generate
	uv run --group docs zensical serve

docs-clean:
	$(RM_SITE)
	$(RM_GENERATED_DOCS)

docs-generated-clean:
	$(RM_GENERATED_DOCS)

docs-build: docs-clean
	uv run --group docs python devtools/prepare_docs.py
	uv run --group docs python docs/gen_reference.py --output-dir docs_build
	uv run --group docs python docs/gen_llms.py --docs-dir docs_build --output-file docs_build/llms.txt
	uv run --group docs zensical build --clean --strict

docs-check: docs-build
	uv run --group docs python devtools/check_docs_site.py docs_build site
	uv run --group docs python .github/scripts/check_public_site.py site

clean:
	$(RM) dist/
	$(RM) *.egg-info/
	$(RM) .pytest_cache/
	$(RM) .mypy_cache/
	$(RM) .venv/
	$(FIND_PYCACHE)
