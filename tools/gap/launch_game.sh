#!/usr/bin/env bash
#
# launch_game.sh — start DevilutionX with the GAP AI companion wired in.
#
# You play slot 0; the AI companion is loaded into slot 1 from its own save.
# After this launches, host a multiplayer game from the menu (pick your slot-0
# hero), then start the agent in another terminal:
#
#   uv run orchestrator.py --model qwen2.5:3b --chat-model gemma3:12b --password foo
#
# Usage:
#   ./launch_game.sh                 # defaults: slot 1, multi_1.sv
#   ./launch_game.sh -- --verbose    # pass extra args through to devilutionx
#   COMPANION_SLOT=2 COMPANION_SAVE=multi_2.sv ./launch_game.sh
#
set -euo pipefail

# Resolve paths relative to this script so it works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BINARY="${DEVILUTIONX_BIN:-$REPO_ROOT/build/devilutionx}"

# Companion configuration (override via env).
COMPANION_SLOT="${COMPANION_SLOT:-1}"
COMPANION_SAVE="${COMPANION_SAVE:-multi_1.sv}"

# Anything after a literal `--` is forwarded verbatim to devilutionx.
EXTRA_ARGS=()
if [[ "${1:-}" == "--" ]]; then
    shift
    EXTRA_ARGS=("$@")
fi

if [[ ! -x "$BINARY" ]]; then
    echo "❌ devilutionx binary not found or not executable: $BINARY" >&2
    echo "   Build it first:" >&2
    echo "   cmake --build $REPO_ROOT/build --target devilutionx" >&2
    exit 1
fi

# Best-effort sanity check that the companion save exists (don't hard-fail —
# the data dir can vary by config).
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/diasurgical/devilution"
if [[ -d "$DATA_DIR" && ! -f "$DATA_DIR/$COMPANION_SAVE" ]]; then
    echo "⚠️  Companion save '$COMPANION_SAVE' not found in $DATA_DIR" >&2
    echo "    Create a multiplayer hero for slot $COMPANION_SLOT first, or set COMPANION_SAVE." >&2
fi

echo "🎮 Launching DevilutionX"
echo "   binary:    $BINARY"
echo "   you:       slot 0"
echo "   companion: slot $COMPANION_SLOT  (save: $COMPANION_SAVE)"
echo "   next:      host a multiplayer game, then start the agent (see header)"
echo

# -n skips the startup videos for faster dev iteration. Drop SKIP_VIDEOS=0 to keep them.
SKIP_VIDEOS_ARG=()
if [[ "${SKIP_VIDEOS:-1}" == "1" ]]; then
    SKIP_VIDEOS_ARG=(-n)
fi

exec "$BINARY" \
    "${SKIP_VIDEOS_ARG[@]}" \
    --companion-save "$COMPANION_SAVE" \
    --companion-slot "$COMPANION_SLOT" \
    "${EXTRA_ARGS[@]}"
