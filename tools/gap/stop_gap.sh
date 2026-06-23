#!/usr/bin/env bash
#
# stop_gap.sh — tear down GAP AI clients/agents cleanly.
#
# The stacked-restart trap: only ONE orchestrator can hold a given GAP socket,
# so leftover agents fighting for it cause confusing "fix didn't take" behavior.
# This script kills them deterministically. (launch_agent.sh is also self-cleaning
# per-socket, so re-running it already restarts that one agent.)
#
# Usage:
#   ./stop_gap.sh                 # stop ALL GAP agents (orchestrators) only
#   ./stop_gap.sh multi_2.sv      # stop just the agent for that hero
#   ./stop_gap.sh --all           # stop ALL agents AND headless clients
#   ./stop_gap.sh --all multi_2   # stop the agent AND headless client for multi_2
#
# Your own (human) client is never touched — it isn't headless and has no GAP socket.
set -uo pipefail

ALL=0
HERO=""
for arg in "$@"; do
    case "$arg" in
        --all) ALL=1 ;;
        *) HERO="${arg%.sv}" ;;  # accept "multi_2" or "multi_2.sv"
    esac
done

# Build the match for the socket stem (empty HERO => match any multi_* socket).
if [[ -n "$HERO" ]]; then
    SOCK_MATCH="devilutionx-gap-${HERO}.sock"
    SAVE_MATCH="companion-save ${HERO}.sv"
    LABEL="$HERO"
else
    SOCK_MATCH="devilutionx-gap-.*\.sock"
    SAVE_MATCH="companion-save multi_"
    LABEL="all"
fi

kill_pattern() {
    local what="$1" pat="$2"
    if pgrep -f "$pat" > /dev/null 2>&1; then
        echo "🛑 stopping $what ($LABEL)"
        pkill -f "$pat"
        for _ in $(seq 1 30); do
            pgrep -f "$pat" > /dev/null 2>&1 || break
            sleep 0.1
        done
        pkill -9 -f "$pat" 2>/dev/null || true
    else
        echo "   no $what running ($LABEL)"
    fi
}

# Agents (orchestrators) — always stopped.
kill_pattern "agent(s)" "orchestrator.py.*${SOCK_MATCH}"

# Headless clients — only with --all (they hold your shared game state; stopping
# one drops that AI player from your hosted game).
if [[ "$ALL" == "1" ]]; then
    kill_pattern "headless client(s)" "devilutionx.*--headless.*${SAVE_MATCH}"
fi

echo "✅ done"
