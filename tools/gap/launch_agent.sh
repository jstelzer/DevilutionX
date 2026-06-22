#!/usr/bin/env bash
#
# launch_agent.sh — start the GAP AI companion agent (orchestrator).
#
# Run this AFTER the game is up and hosting (see launch_game.sh) — the agent
# connects to the Unix socket the game opens.
#
# Defaults to the "split" model config: a fast model for the dungeon/tactical
# loop and a stronger one for chat. Override any of these via env vars.
#
# Usage:
#   ./launch_agent.sh                          # split: qwen2.5:3b + gemma3:12b
#   CHAT_MODEL=gemma3:27b ./launch_agent.sh    # richer chat
#   MODEL=gemma3:12b ./launch_agent.sh         # heavier tactical reasoning
#   PASSWORD=secret ./launch_agent.sh          # match the hosted game's password
#   ./launch_agent.sh -- --debug               # forward extra args to orchestrator
#
set -euo pipefail

# Resolve paths relative to this script so it works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Config (override via env).
MODEL="${MODEL:-qwen2.5:3b}"
CHAT_MODEL="${CHAT_MODEL:-gemma3:12b}"
PASSWORD="${PASSWORD:-foo}"
SOCKET="${SOCKET:-/tmp/devilutionx-gap.sock}"

# Anything after a literal `--` is forwarded verbatim to the orchestrator.
EXTRA_ARGS=()
if [[ "${1:-}" == "--" ]]; then
    shift
    EXTRA_ARGS=("$@")
fi

if ! command -v uv &> /dev/null; then
    echo "❌ uv not found. Install it, then run ./setup.sh to create the venv." >&2
    exit 1
fi

# The game must be running and hosting first — that's what creates the socket.
if [[ ! -S "$SOCKET" ]]; then
    echo "⚠️  GAP socket not found at $SOCKET" >&2
    echo "    Start the game and host a multiplayer game first (./launch_game.sh)." >&2
    echo "    Waiting up to 30s for it to appear..." >&2
    for _ in $(seq 1 30); do
        [[ -S "$SOCKET" ]] && break
        sleep 1
    done
    if [[ ! -S "$SOCKET" ]]; then
        echo "❌ Still no socket — is the game hosting? Aborting." >&2
        exit 1
    fi
fi

echo "🤖 Launching GAP agent"
echo "   dungeon model: $MODEL"
echo "   chat model:    $CHAT_MODEL"
echo "   socket:        $SOCKET"
echo

exec uv run orchestrator.py \
    --model "$MODEL" \
    --chat-model "$CHAT_MODEL" \
    --password "$PASSWORD" \
    --socket "$SOCKET" \
    "${EXTRA_ARGS[@]}"
