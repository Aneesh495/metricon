SHELL := /bin/bash
METRICON_ROOT ?= .metricon
PYTHON := .venv/bin/python
METRICON := .venv/bin/metricon --root $(METRICON_ROOT)

.PHONY: bootstrap dev demo test test-integration test-e2e dataset-public experiment benchmark acceptance verify
bootstrap:
	uv sync --locked --python 3.13
	npm ci
	npm run build
	uv build --wheel --out-dir $(METRICON_ROOT)/build

dev:
	METRICON_HOME=$(METRICON_ROOT) $(PYTHON) scripts/dev.py

demo:
	$(METRICON) demo

test:
	.venv/bin/ruff check src tests scripts
	.venv/bin/pytest -q
	npm run check
	npm run test:web
	npm run build

test-integration:
	$(PYTHON) scripts/integration.py --root $(METRICON_ROOT)

test-e2e:
	npm run build
	npm run test:e2e

dataset-public:
	$(PYTHON) scripts/research.py dataset --root $(METRICON_ROOT)

experiment:
	$(PYTHON) scripts/research.py experiment --root $(METRICON_ROOT)

benchmark:
	$(METRICON) benchmark

acceptance:
	$(METRICON) acceptance

verify:
	$(METRICON) verify
