SHELL := /bin/bash
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
export PYTHONPATH := backend

.PHONY: help setup data data-offline synthetic dev backend frontend mcp inspector test bench reset-demo deploy seed-firestore lint

help:
	@echo "make setup        - create .venv + install backend & frontend deps"
	@echo "make data         - fetch public APU feed -> pseudonymise -> snapshot, then generate mocks + synthetic students"
	@echo "make data-offline - regenerate mocks + synthetic data from the committed snapshot only (no network)"
	@echo "make dev          - backend :8000 (REST + MCP at /mcp) + dashboard :3000 (+ Firestore emulator if STORE_BACKEND=firestore)"
	@echo "make test         - backend tests incl. solver property tests"
	@echo "make mcp          - run the MCP server alone on :8001/mcp ; make inspector - open MCP Inspector (stdio)"
	@echo "make reset-demo   - restore a clean demo state (<10 s)"
	@echo "make deploy       - build & deploy backend + frontend to Cloud Run (asia-southeast1)"

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q --upgrade pip
	.venv/bin/pip install -q -e "backend[dev]"
	cd frontend && npm install

data:
	$(PY) scripts/fetch_timetable.py
	$(PY) scripts/generate_synthetic.py

data-offline synthetic:
	$(PY) scripts/generate_synthetic.py

backend:
	cd backend && ../$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app

frontend:
	cd frontend && npm run dev

dev:
	@if [ "$$STORE_BACKEND" = "firestore" ]; then \
	  (gcloud emulators firestore start --host-port=localhost:8080 >/tmp/fs-emulator.log 2>&1 &) ; \
	  export FIRESTORE_EMULATOR_HOST=localhost:8080 ; fi ; \
	trap 'kill 0' EXIT ; \
	(cd backend && ../$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app) & \
	(cd frontend && npm run dev) & \
	wait

mcp:
	cd backend && ../$(PY) -m app.mcp_server

inspector:
	npx @modelcontextprotocol/inspector $(abspath $(PY)) -m app.mcp_server --stdio

test:
	cd backend && ../$(PY) -m pytest -q

bench:
	$(PY) scripts/benchmark.py

reset-demo:
	$(PY) scripts/reset_demo.py

seed-firestore:
	STORE_BACKEND=firestore $(PY) scripts/seed_firestore.py

deploy:
	bash scripts/deploy.sh
