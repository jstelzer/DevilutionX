#!/usr/bin/env bash
#
# launch_headless.sh — start the AI's OWN headless devilutionx client (GAP-TRUE-MP).
#
# This is the new true-multiplayer model: the AI is a real player-2 in its own
# client, not a slot in yours. It joins a TCP game YOU host from a normal client.
#
# Order of operations:
#   1. In your normal client: Multiplayer -> TCP/IP -> Host Game (password foo),
#      pick your multi_0 hero. (No GAP/companion flags on your client.)
#   2. Run this script (the AI's headless client joins as player 2 / multi_1).
#   3. Run ./launch_agent.sh (the orchestrator connects to the GAP socket this
#      headless client owns).
#
# Uses dummy SDL drivers so there's no window and no GPU/audio use; all state
# reaches the AI over the GAP DSL socket.
#
# Usage:
#   ./launch_headless.sh                       # join 127.0.0.1:6112, password foo, hero multi_1.sv
#   JOIN=127.0.0.1:6112 PASSWORD=foo HERO=multi_1.sv ./launch_headless.sh
#
# Multiple AI players: run one headless client per hero save. Each binds its own
# GAP socket, derived from the save stem (multi_2.sv -> /tmp/devilutionx-gap-multi_2.sock),
# so a second client never collides with the first. e.g. a Sorc as player 3:
#   HERO=multi_2.sv ./launch_headless.sh       # then: HERO=multi_2.sv ./launch_agent.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BINARY="${DEVILUTIONX_BIN:-$REPO_ROOT/build/devilutionx}"

JOIN="${JOIN:-127.0.0.1:6112}"
PASSWORD="${PASSWORD:-foo}"
HERO="${HERO:-multi_1.sv}"

if [[ ! -x "$BINARY" ]]; then
    echo "❌ devilutionx not found: $BINARY (build it first)" >&2
    exit 1
fi

echo "🤖 Launching HEADLESS AI client"
echo "   join:     $JOIN"
echo "   hero:     $HERO"
echo "   socket:   /tmp/devilutionx-gap-${HERO%.sv}.sock"
echo "   (host a TCP game from your normal client first; then run HERO=$HERO ./launch_agent.sh)"
echo

# Dummy SDL drivers → no window, no GPU/audio. --headless makes rendering a no-op.
exec env SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy "$BINARY" \
    --diablo -n \
    --headless \
    --join "$JOIN" \
    --game-password "$PASSWORD" \
    --companion-save "$HERO"
