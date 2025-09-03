# GAP AI Development Makefile

.PHONY: help setup install dev-install clean test validate format lint run debug

help:  ## Show this help message
	@echo "GAP AI Development Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup:  ## Set up development environment (interactive)
	@./setup.sh

install:  ## Quick install with uv (non-interactive)
	@echo "📦 Installing GAP AI with uv..."
	@command -v uv >/dev/null 2>&1 || (echo "❌ uv not found. Run 'make setup' for guided installation." && exit 1)
	@uv venv --seed
	@uv pip install -e .

dev-install:  ## Install with development dependencies
	@echo "📦 Installing GAP AI with dev dependencies..."
	@command -v uv >/dev/null 2>&1 || (echo "❌ uv not found. Run 'make setup' for guided installation." && exit 1)
	@uv venv --seed
	@uv pip install -e ".[dev]"

clean:  ## Clean up environment and cache files
	@echo "🧹 Cleaning up..."
	@rm -rf .venv
	@rm -rf __pycache__ **/__pycache__
	@rm -rf *.pyc **/*.pyc
	@rm -rf .pytest_cache
	@rm -rf gap_logs
	@echo "✅ Cleanup complete"

test: dev-install  ## Run all tests
	@echo "🧪 Running tests..."
	@uv run pytest -v

validate:  ## Run Phase 0 validation tests
	@echo "🔍 Running validation tests..."
	@if [ -d ".venv" ]; then \
		source .venv/bin/activate && python validation_tests.py; \
	else \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi

format: dev-install  ## Format code with black
	@echo "🎨 Formatting code..."
	@uv run black *.py

lint: dev-install  ## Lint code with ruff
	@echo "🔍 Linting code..."
	@uv run ruff check *.py

run:  ## Run the GAP AI agent (requires PASSWORD env var)
	@if [ -z "$(PASSWORD)" ]; then \
		echo "❌ PASSWORD environment variable required"; \
		echo "Usage: make run PASSWORD=your_password"; \
		exit 1; \
	fi
	@echo "🤖 Starting GAP AI agent..."
	@if [ -d ".venv" ]; then \
		source .venv/bin/activate && python mcp_server.py --password $(PASSWORD); \
	else \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi

debug:  ## Run debug tools
	@echo "🐛 Running debug tools..."
	@if [ -d ".venv" ]; then \
		source .venv/bin/activate && python debug_tools.py; \
	else \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi

# Development workflow targets
dev: dev-install validate  ## Full development setup
	@echo "🎉 Development environment ready!"

check: format lint test  ## Run all quality checks

# Build DevilutionX with GAP support
build-game:  ## Build DevilutionX with GAP enabled
	@echo "🔨 Building DevilutionX with GAP support..."
	@cd ../.. && mkdir -p build && cd build
	@cd ../../build && cmake -DENABLE_GAP=ON .. && make -j8

# Quick development cycle
quick-test: validate  ## Quick validation test
	@echo "✅ Quick test complete"
