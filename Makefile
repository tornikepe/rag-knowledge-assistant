.PHONY: install dev run test seed clean docker

install:       ## Install dependencies
	pip install -r requirements.txt

run:           ## Start the API + UI at http://localhost:8000
	uvicorn app.main:app --reload --port 8000

test:          ## Run the offline test suite
	pytest

seed:          ## Ingest the bundled sample document
	python scripts/ingest_sample.py

docker:        ## Build and run with Docker Compose
	docker compose up --build

clean:         ## Remove the persisted index and caches
	rm -rf storage .pytest_cache **/__pycache__

help:          ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
