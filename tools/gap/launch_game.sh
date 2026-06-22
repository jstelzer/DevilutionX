#!/usr/bin/env bash
#
# launch_game.sh — start YOUR normal DevilutionX client (GAP-TRUE-MP model).
#
# In the true-multiplayer model the AI is its OWN headless client (player 2),
# not a slot in yours — so your client passes NO companion flags. You just host
# a TCP game and play normally.
#
# Full flow:
#   1. ./launch_game.sh  → in-game: Multiplayer -> TCP/IP -> Host Game
#      (password foo), pick your multi_0 hero.
#   2. ./launch_headless.sh  → the AI's headless client joins as player 2.
#   3. ./launch_agent.sh     → the orchestrator connects to the GAP socket.
#
# Usage:
#   ./launch_game.sh                 # plain client
#   ./launch_game.sh -- --verbose    # pass extra args through to devilutionx
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BINARY="${DEVILUTIONX_BIN:-$REPO_ROOT/build/devilutionx}"

# Anything after a literal `--` is forwarded verbatim to devilutionx.
EXTRA_ARGS=()
if [[ "${1:-}" == "--" ]]; then
    shift
    EXTRA_ARGS=("$@")
fi

if [[ ! -x "$BINARY" ]]; then
    echo "❌ devilutionx binary not found: $BINARY (build it first)" >&2
    exit 1
fi

echo "🎮 Launching your DevilutionX client"
echo "   next: Multiplayer -> TCP/IP -> Host Game (password foo), pick multi_0,"
echo "         then ./launch_headless.sh and ./launch_agent.sh"
echo

# -n skips startup videos. Drop SKIP_VIDEOS=0 to keep them.
SKIP_VIDEOS_ARG=()
if [[ "${SKIP_VIDEOS:-1}" == "1" ]]; then
    SKIP_VIDEOS_ARG=(-n)
fi

exec "$BINARY" "${SKIP_VIDEOS_ARG[@]}" "${EXTRA_ARGS[@]}"
