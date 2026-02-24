.PHONY: setup start api web test lint clean

# First-time setup: install all dependencies
setup:
	./setup.sh

# Start both API and web servers
start:
	./start.sh

# Start only the API (port 8000)
api:
	cd apps/api && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start only the web dev server (port 3000)
web:
	pnpm --filter web dev

# Run Python unit tests
test:
	cd apps/api && source .venv/bin/activate && python -m pytest tests/ -v

# Run Playwright e2e tests (requires start.sh to be running)
e2e:
	pnpm --filter web exec playwright test

# Lint Python
lint:
	cd apps/api && source .venv/bin/activate && python -m ruff check app/

# Install a new Python package and save to requirements.txt
# Usage: make pip pkg=httpx
pip:
	cd apps/api && source .venv/bin/activate && pip install "$(pkg)" && pip freeze | grep -i "$(pkg)" >> requirements.txt

# Remove build artifacts
clean:
	rm -rf apps/web/.next packages/shared/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
