#!/usr/bin/env python3
"""Track E offline analyzer — mine traces/*.jsonl for decision pathologies.

The decision tracer (``decision_tracer.py``) writes one JSONL record per
``decide()`` *change* (log-on-change dedup; ``repeats`` = how many think-cycles
the decision held before it changed). This tool reads that corpus and reports the
pathologies the roadmap (Track E / B5) names, so weight tuning becomes
"measure → change → re-measure" instead of vibes:

- **compression** = ticks / records. High = stable (a decision held many ticks);
  ~1x = thrashing (a new decision every cycle). The headline churn metric.
- **thrash%** = share of records that held 0 extra cycles (changed immediately).
- **oscillation** = A→B→A flips; the top *2-cycle pair* is the ping-pong culprit
  (e.g. Town↔Movement — the follow-hysteresis bug found 2026-06-30).
- **winner share / starvation** = who wins; agents recommended but never winning.
- **llm calls by agent** = the real inference cost (recorded per fired LLM agent).

Usage:
    uv run python trace_stats.py                # all of traces/*.jsonl
    uv run python trace_stats.py traces/foo.jsonl [more...]
    ./dev.sh stats
"""
from __future__ import annotations

import glob
import json
import sys
from collections import Counter

# Tier ≥8 "reflex/tactical" vs ≤7 "leaseable" split is in the orchestrator; here
# we only need the set that actually calls the LLM, to attribute inference cost.
LLM_AGENTS = {"Combat", "Chat", "Shopping", "Griswold", "Adria"}


def _load(path: str) -> list:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # tolerate a torn final line from a live-killed session
    return out


def analyze(path: str) -> dict | None:
    recs = _load(path)
    if not recs:
        return None
    n = len(recs)
    ticks = sum(r.get("repeats", 0) + 1 for r in recs)
    winners = [r["winner"] for r in recs]
    win = Counter(winners)
    town = sum(1 for r in recs if r.get("in_town"))
    thrash = sum(1 for r in recs if r.get("repeats", 0) == 0)

    # A→B→A oscillation + directed transition counts (the ping-pong fingerprint).
    osc = 0
    trans: Counter = Counter()
    for i in range(1, n):
        a, b = winners[i - 1], winners[i]
        if a != b:
            trans[(a, b)] += 1
        if i >= 2 and winners[i] == winners[i - 2] and winners[i] != winners[i - 1]:
            osc += 1

    # recommended-but-never-won = starvation candidates
    recommended = set()
    for r in recs:
        for rec in r.get("recommendations", []):
            recommended.add(rec["agent"])
    starved = sorted(recommended - set(win))

    llm_by_agent: Counter = Counter()
    for r in recs:
        for e in r.get("llm", []):
            llm_by_agent[e["agent"]] += 1

    return {
        "path": path.split("/")[-1],
        "records": n,
        "ticks": ticks,
        "compression": round(ticks / n, 1),
        "town_pct": round(100 * town / n),
        "thrash_pct": round(100 * thrash / n),
        "osc": osc,
        "winners": win,
        "transitions": trans,
        "starved": starved,
        "llm_by_agent": llm_by_agent,
    }


def _top_cycle(trans: Counter) -> str | None:
    """Strongest 2-cycle: the (a,b) where both a→b and b→a fire a lot."""
    best, best_score = None, 0
    for (a, b), c in trans.items():
        back = trans.get((b, a), 0)
        score = min(c, back)  # a true ping-pong needs both directions
        if score > best_score:
            best, best_score = (a, b), score
    if not best or best_score == 0:
        return None
    a, b = best
    return f"{a}<->{b} x{best_score}"


def main(argv: list) -> int:
    files = argv or sorted(glob.glob("traces/*.jsonl"))
    if not files:
        print("no trace files (pass paths, or capture with TRACE=1 ./launch_agent.sh)")
        return 1

    tot_ticks = tot_recs = 0
    agg_win: Counter = Counter()
    agg_llm: Counter = Counter()
    agg_trans: Counter = Counter()
    for p in files:
        r = analyze(p)
        if not r:
            continue
        tot_ticks += r["ticks"]
        tot_recs += r["records"]
        agg_win.update(r["winners"])
        agg_llm.update(r["llm_by_agent"])
        agg_trans.update(r["transitions"])
        cyc = _top_cycle(r["transitions"]) or "-"
        print(
            f"\n{r['path']}\n"
            f"  records={r['records']} ticks={r['ticks']} "
            f"compression={r['compression']}x town={r['town_pct']}% "
            f"thrash={r['thrash_pct']}% osc={r['osc']} cycle={cyc}"
        )
        print(f"  winners: {r['winners'].most_common(6)}")
        if r["llm_by_agent"]:
            print(f"  llm:     {r['llm_by_agent'].most_common()}")
        if r["starved"]:
            print(f"  starved: {r['starved']}")

    print("\n=== AGGREGATE ===")
    print(
        f"files={len(files)} records={tot_recs} ticks={tot_ticks} "
        f"compression={round(tot_ticks / max(tot_recs, 1), 1)}x"
    )
    print(f"top 2-cycle (ping-pong): {_top_cycle(agg_trans) or '-'}")
    print(f"winner share: {agg_win.most_common(12)}")
    print(f"llm calls by agent: {agg_llm.most_common() or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
