.PHONY: install-services compose-up compose-down

install-services:
	@echo "Installing service dependencies..."
	pip install -r services/ingest_api/requirements.txt
	pip install -r services/orchestrator/requirements.txt
	pip install -r services/extractors/requirements.txt
	pip install -r services/qa_loop/requirements.txt
	pip install -r services/artifact-builder/requirements.txt

compose-up:
	docker-compose up --build

compose-down:
	docker-compose down
