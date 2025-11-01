#!/bin/bash
# Launcher for GAP Multi-Agent Council Orchestrator

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default settings
# Dungeon model: Fast 3B for quick combat decisions
# Town model: Smart 8B for sophisticated town interactions & chat
DUNGEON_MODEL="${DUNGEON_MODEL:-qwen2.5:3b}"
TOWN_MODEL="${TOWN_MODEL:-llama3.1:8b}"
PASSWORD="${PASSWORD:-foo}"
THINK_INTERVAL="${THINK_INTERVAL:-1.0}"  # 1 second for responsive gameplay

echo "================================================"
echo "GAP Multi-Agent Council Orchestrator"
echo "================================================"
echo "Dungeon model: $DUNGEON_MODEL (fast combat)"
echo "Town model: $TOWN_MODEL (sophisticated interactions)"
echo "Think interval: ${THINK_INTERVAL}s"
echo "Password: $PASSWORD"
echo "================================================"
echo "Agents: Combat, Healing, Loot, Stats, Town, Movement"
echo "Strategy: Context-based model switching"
echo "================================================"
echo

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "❌ Ollama is not running!"
    echo "   Start it with: ollama serve"
    exit 1
fi

# Check if dungeon model is available
if ! ollama list | grep -q "$DUNGEON_MODEL"; then
    echo "⚠️  Dungeon model $DUNGEON_MODEL not found"
    echo "   Pulling it now..."
    ollama pull "$DUNGEON_MODEL"
fi

# Check if town model is available
if ! ollama list | grep -q "$TOWN_MODEL"; then
    echo "⚠️  Town model $TOWN_MODEL not found"
    echo "   Pulling it now..."
    ollama pull "$TOWN_MODEL"
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

# Run multi-agent orchestrator with context-based model switching
python3 orchestrator.py \
    --model "$DUNGEON_MODEL" \
    --chat-model "$TOWN_MODEL" \
    --password "$PASSWORD" \
    --think-interval "$THINK_INTERVAL" \
    "$@"
