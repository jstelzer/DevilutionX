#!/bin/bash
# Quick development helper. Uses uv, so no manual venv activation needed.

set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

case "${1:-help}" in
    "run")
        # Launch the agent (waits for the game socket, then connects).
        exec ./launch_agent.sh
        ;;
    "test")
        echo "🧪 Running tests..."
        uv run python -m pytest test_personality.py -q
        uv run python dsl_parser.py
        uv run python decision_tracer.py
        ;;
    "format")
        echo "🎨 Formatting code..."
        uv run black .
        ;;
    "lint")
        echo "🔍 Linting code..."
        uv run ruff check .
        ;;
    "fix")
        echo "🔧 Auto-fixing lint issues..."
        uv run ruff check --fix .
        ;;
    "clean")
        echo "🧹 Cleaning up..."
        rm -rf __pycache__ agents/__pycache__ *.pyc .pytest_cache gap_logs/*.log agent.log ai-player.log traces/ 2>/dev/null || true
        echo "✅ Cleanup complete"
        ;;
    "help"|*)
        echo "🛠️  GAP AI Development Helper"
        echo ""
        echo "Usage: ./dev.sh <command>"
        echo ""
        echo "Commands:"
        echo "  run      - Launch the AI companion agent (see launch_agent.sh)"
        echo "  test     - Run personality tests + DSL parser & decision-tracer self-tests"
        echo "  format   - Format code with black"
        echo "  lint     - Check code with ruff"
        echo "  fix      - Auto-fix lint issues with ruff"
        echo "  clean    - Remove caches and logs"
        echo "  help     - Show this help"
        ;;
esac
