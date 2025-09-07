#!/bin/bash
# Quick development helper script

set -e

# Activate venv if not already activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    source .venv/bin/activate
fi

# Parse command
case "${1:-help}" in
    "run")
        echo "🚀 Running enhanced MCP server..."
        python mcp_server.py --model qwen2.5:3b --companion-slot 1 --password "${2:-foo}"
        ;;
    "test")
        echo "🧪 Running validation tests..."
        python validation_tests.py
        ;;
    "format")
        echo "🎨 Formatting code..."
        black *.py
        ;;
    "lint")
        echo "🔍 Linting code..." 
        ruff check *.py
        ;;
    "fix")
        echo "🔧 Auto-fixing linting issues..."
        ruff check --fix *.py
        ;;
    "combat")
        echo "⚔️  Running combat agent..."
        python combat_gap_agent.py --password "${2:-foo}"
        ;;
    "simple")
        echo "🤖 Running simple LLM bridge..."
        python simple_bridge.py --model "${2:-qwen2.5:3b}" --password foo
        ;;
    "debug")
        echo "🔍 Running debug tools..."
        python debug_tools.py
        ;;
    "clean")
        echo "🧹 Cleaning up..."
        rm -rf __pycache__ *.pyc .pytest_cache gap_logs/*.log agent.log ai-player.log debug_raw_json.txt 2>/dev/null || true
        echo "✅ Cleanup complete"
        ;;
    "help"|*)
        echo "🛠️  GAP AI Development Helper"
        echo ""
        echo "Usage: ./dev.sh <command> [args]"
        echo ""
        echo "Commands:"
        echo "  run [password]    - Run enhanced MCP server (default password: foo)"
        echo "  simple [model]    - Run simple LLM bridge (default model: qwen2.5:3b)"
        echo "  combat [password] - Run combat agent (default password: foo)"
        echo "  test              - Run validation tests"
        echo "  format            - Format code with black"
        echo "  lint              - Check code with ruff"
        echo "  fix               - Auto-fix linting issues"
        echo "  debug             - Run debug tools"
        echo "  clean             - Clean up logs and cache files"
        echo "  help              - Show this help"
        echo ""
        echo "Examples:"
        echo "  ./dev.sh run mypassword    # Run with custom password"
        echo "  ./dev.sh test              # Run all tests"
        echo "  ./dev.sh format && ./dev.sh lint  # Format and check code"
        ;;
esac