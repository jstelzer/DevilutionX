#!/bin/bash
# Simple launcher for DSL GAP Agent

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default settings - optimized for 7-8B models
MODEL="${MODEL:-llama3.1:latest}"
PASSWORD="${PASSWORD:-foo}"
THINK_INTERVAL="${THINK_INTERVAL:-1.0}"  # 1 second for responsive gameplay

echo "=================================="
echo "DSL GAP Agent Launcher"
echo "=================================="
echo "Model: $MODEL"
echo "Think interval: ${THINK_INTERVAL}s"
echo "Password: $PASSWORD"
echo "=================================="
echo

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "❌ Ollama is not running!"
    echo "   Start it with: ollama serve"
    exit 1
fi

# Check if model is available
if ! ollama list | grep -q "$MODEL"; then
    echo "⚠️  Model $MODEL not found"
    echo "   Pulling it now..."
    ollama pull "$MODEL"
fi

echo "✅ Ollama ready"
echo

# Check if socket exists (game running)
if [ ! -S /tmp/devilutionx-gap.sock ]; then
    echo "⚠️  GAP socket not found"
    echo "   Make sure DevilutionX is running with:"
    echo "   ./devilutionx --companion-save multi_1.sv --companion-slot 1"
    echo
    echo "   Waiting for socket..."
    while [ ! -S /tmp/devilutionx-gap.sock ]; do
        sleep 1
    done
    echo "✅ Socket found!"
fi

# Run agent
python3 dsl_agent.py \
	--debug \
    --model "$MODEL" \
    --password "$PASSWORD" \
    --think-interval "$THINK_INTERVAL" \
    "$@"
