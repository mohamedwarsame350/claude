.PHONY: up down demo-flow test logs clean

PYTHON ?= python3

up:
	docker compose up --build -d
	@echo "Waiting for services to be healthy (up to 60s)..."
	@docker compose ps

down:
	docker compose down -v

demo-flow: up
	@echo "Giving services 15s to finish startup..."
	@sleep 15
	$(PYTHON) demo.py

test:
	@echo "Installing test dependencies..."
	$(PYTHON) -m pip install -q -r tests/requirements.txt
	$(PYTHON) -m pytest tests/ -v --tb=short

logs:
	docker compose logs -f

clean:
	docker compose down -v --rmi local 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f demo.db
