#!/bin/bash
# Quick integration test for DSL GAP system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=================================="
echo "DSL GAP Integration Test"
echo "=================================="
echo

# Test 1: DSL Parser
echo "📝 Test 1: DSL Parser"
cd "$SCRIPT_DIR"
python3 dsl_parser.py > /tmp/dsl_parser_test.log 2>&1
if [ $? -eq 0 ]; then
    echo "✅ DSL parser works"
else
    echo "❌ DSL parser failed"
    cat /tmp/dsl_parser_test.log
    exit 1
fi
echo

# Test 2: Memory Store
echo "🧠 Test 2: Memory Store"
python3 memory_store.py > /tmp/memory_test.log 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Memory store works"
    rm -f test_memory.db
else
    echo "❌ Memory store failed"
    cat /tmp/memory_test.log
    exit 1
fi
echo

# Test 3: Check game binary
echo "🎮 Test 3: Game Binary"
GAME_BIN="$PROJECT_ROOT/build/devilutionx"
if [ -f "$GAME_BIN" ]; then
    echo "✅ Game binary exists: $GAME_BIN"
else
    echo "❌ Game binary not found!"
    echo "   Build with: cd build && make -j8"
    exit 1
fi
echo

# Test 4: Check Ollama
echo "🤖 Test 4: Ollama"
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama is running"

    # Check for recommended model
    if ollama list | grep -q "qwen2.5:3b"; then
        echo "✅ qwen2.5:3b model available"
    else
        echo "⚠️  qwen2.5:3b not found"
        echo "   Pull it with: ollama pull qwen2.5:3b"
    fi
else
    echo "❌ Ollama not running"
    echo "   Start it with: ollama serve"
    exit 1
fi
echo

echo "=================================="
echo "✅ All tests passed!"
echo "=================================="
echo
echo "Ready to run:"
echo "  1. Start game: $GAME_BIN --companion-save multi_1.sv --companion-slot 1"
echo "  2. Run agent: cd $SCRIPT_DIR && ./run_agent.sh"
echo
