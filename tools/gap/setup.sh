#!/bin/bash
# GAP AI Development Environment Setup Script

set -e

echo "🚀 Setting up GAP AI development environment..."

# Check if uv is installed, if not offer to install it
if ! command -v uv &> /dev/null; then
    echo "📦 uv not found. Installing uv (modern Python package manager)..."
    echo "This is faster and more reliable than traditional venv + pip"
    echo ""
    read -p "Install uv? [Y/n]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "❌ uv installation declined. Using traditional venv + pip instead..."
        USE_TRADITIONAL=1
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
        source $HOME/.cargo/env 2>/dev/null || true
        export PATH="$HOME/.cargo/bin:$PATH"
        USE_TRADITIONAL=0
    fi
else
    echo "✅ uv found"
    USE_TRADITIONAL=0
fi

# Set up Python environment
if [ "$USE_TRADITIONAL" = "1" ]; then
    echo "📁 Creating traditional Python virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    # Deps are declared in pyproject.toml; install runtime + dev tools explicitly
    # (no build backend, so we can't `pip install .`).
    pip install requests pytest pytest-asyncio black ruff
    echo "✅ Traditional venv setup complete"
    echo "💡 To activate: source .venv/bin/activate"
else
    echo "📁 Creating uv-managed Python environment..."
    echo "📦 Syncing dependencies from pyproject.toml with uv..."
    # uv sync reads [project.dependencies] + the dev extra; creates .venv automatically.
    uv sync --extra dev
    echo "✅ uv setup complete"
    echo "💡 To activate: source .venv/bin/activate"
fi

echo ""
echo "🧪 Running validation tests to verify setup..."
if [ "$USE_TRADITIONAL" = "1" ]; then
    source .venv/bin/activate && python3 -m pytest test_personality.py -q && python3 dsl_parser.py
else
    uv run python -m pytest test_personality.py -q && uv run python dsl_parser.py
fi

echo ""
echo "🎉 GAP AI development environment is ready!"
echo ""
echo "Usage:"
echo "  Activate environment: source .venv/bin/activate"
if [ "$USE_TRADITIONAL" = "0" ]; then
    echo "  Run with uv:          uv run python <script>"
    echo "  Add dependency:       uv add <package>"
fi
echo "  Run orchestrator:     uv run orchestrator.py --companion-slot 1 --model qwen2.5:3b --password <password>"
echo "  Run tests:            uv run python -m pytest test_personality.py -q"
echo "  Lint:                 uv run ruff check ."
echo ""
echo "Development tools:"
echo "  Format code:          black *.py"
echo "  Lint code:            ruff check *.py"
echo "  Run tests:            pytest"