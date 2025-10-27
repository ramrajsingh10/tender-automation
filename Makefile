.PHONY: install-services compose-up compose-down

install-services:
	@echo "Installing service dependencies..."
	pip install -r backend/requirements.txt
	pip install -r services/orchestrator/requirements.txt
	pip install -r services/ingest_worker/requirements.txt

compose-up:
	docker compose up --build

compose-down:
	docker compose down
