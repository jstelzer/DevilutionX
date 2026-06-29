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
#   TRACE=1 ./launch_agent.sh                  # flight-record decisions → traces/<hero>-<ts>.jsonl
#   TRACE=/tmp/run.jsonl ./launch_agent.sh     # ...or to an explicit path
#   HUD=1 ./launch_agent.sh                    # live Emacs cockpit feed → .hud/<hero>.json (M-x gap-hud)
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
# Socket path is per-client, derived from the hero save stem so multiple headless
# clients (e.g. a Rogue on multi_1 and a Sorc on multi_2) don't collide. Must
# match what the headless client binds (see launch_headless.sh / --gap-socket).
HERO="${HERO:-multi_1.sv}"
SOCKET="${SOCKET:-/tmp/devilutionx-gap-${HERO%.sv}.sock}"

# Anything after a literal `--` is forwarded verbatim to the orchestrator.
EXTRA_ARGS=()
if [[ "${1:-}" == "--" ]]; then
    shift
    EXTRA_ARGS=("$@")
fi

# Decision tracing (ROADMAP Track E). TRACE unset → off. TRACE=1/true/yes/auto →
# auto-named file under traces/ (keyed by hero + timestamp, so multiple clients
# and successive runs never clobber each other). Any other value is taken as an
# explicit output path. The data-capture/replay tooling reads these JSONL files.
TRACE_ARGS=()
if [[ -n "${TRACE:-}" ]]; then
    case "$TRACE" in
        1|true|yes|auto)
            mkdir -p traces
            TRACE_PATH="traces/${HERO%.sv}-$(date +%Y%m%d-%H%M%S).jsonl"
            ;;
        *)
            TRACE_PATH="$TRACE"
            mkdir -p "$(dirname "$TRACE_PATH")"
            ;;
    esac
    TRACE_ARGS=(--trace "$TRACE_PATH")
    echo "📼 Decision trace → $TRACE_PATH"
fi

# Live HUD feed (Emacs cockpit). HUD unset → off. HUD=1/true/yes/auto → a stable
# per-hero file under .hud/ that Emacs gap-hud.el polls (one client = one file,
# so Airhead and Beavis never collide). Any other value is an explicit path.
# Unlike traces/, this is current-truth (last write wins), not an append log.
HUD_ARGS=()
if [[ -n "${HUD:-}" ]]; then
    case "$HUD" in
        1|true|yes|auto)
            mkdir -p .hud
            HUD_PATH=".hud/${HERO%.sv}.json"
            ;;
        *)
            HUD_PATH="$HUD"
            mkdir -p "$(dirname "$HUD_PATH")"
            ;;
    esac
    HUD_ARGS=(--hud "$HUD_PATH")
    echo "🖥️  Live HUD → $HUD_PATH   (M-x gap-hud in Emacs)"
fi

if ! command -v uv &> /dev/null; then
    echo "❌ uv not found. Install it, then run ./setup.sh to create the venv." >&2
    exit 1
fi

# Self-cleaning: kill any orchestrator already bound to THIS socket before we
# start. Only one agent can hold the IPC socket; re-running this script would
# otherwise stack a second agent that fights the first for the connection (and
# silently runs stale code). Matches by the unique --socket path so a sibling
# agent on a different client (e.g. multi_1 vs multi_2) is left untouched.
if pgrep -f "orchestrator.py.*${SOCKET}" > /dev/null 2>&1; then
    echo "♻️  Existing agent on $SOCKET — stopping it first"
    pkill -f "orchestrator.py.*${SOCKET}"
    # Wait for it to release the socket connection (up to ~3s).
    for _ in $(seq 1 30); do
        pgrep -f "orchestrator.py.*${SOCKET}" > /dev/null 2>&1 || break
        sleep 0.1
    done
    pkill -9 -f "orchestrator.py.*${SOCKET}" 2>/dev/null || true
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
    "${TRACE_ARGS[@]}" \
    "${HUD_ARGS[@]}" \
    "${EXTRA_ARGS[@]}"
