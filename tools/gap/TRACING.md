# GAP decision tracing — a field guide

> **Trace before you tune.** The council is almost a pure function
> `state → command`. Record that stream and you can *measure* why she does what
> she does, replay it offline, and check a weight change instead of guessing.
> This is the day-to-day version of ROADMAP **Track E**.

The loop:

```
   ┌─────────── capture ───────────┐   ┌──── analyze ────┐   ┌──── replay ────┐
   TRACE=1 ./launch_agent.sh   →   traces/*.jsonl   →   ./dev.sh stats   →   feed a recorded
   (durable, deduped append log)        (find the pathology)        DSL line back through an
                                                                    agent to pin the cause
   HUD=1 ./launch_agent.sh     →   .hud/<hero>.json  →  M-x gap-hud   (live, current-truth)
```

Two sinks, **one record** (`build_decision_record` in `decision_tracer.py`). The
durable trace and the live HUD render the *same* artifact the tests replay — no
parallel "demo telemetry."

---

## 1. Capture

```bash
TRACE=1 ./launch_agent.sh                 # → traces/<hero>-<ts>.jsonl  (auto-named)
TRACE=/tmp/run.jsonl ./launch_agent.sh    # → explicit path
HUD=1 ./launch_agent.sh                    # → .hud/<hero>.json  (live Emacs cockpit)
TRACE=1 HUD=1 ./launch_agent.sh            # both at once
```

- `traces/` is a **deduped append log** (git-ignored): one record per `decide()`
  **change**. A decision that holds N think-cycles is folded into one record with
  `repeats=N` — so `repeats` is literally the churn metric.
- `.hud/<hero>.json` is **current-truth** (last write wins), wrapped in an
  envelope (`source_id`, `written_at`, `offline`) so Emacs can attribute the
  client and show "stale" without trusting file mtime.
- Multi-client: each toon auto-names by hero, so Airhead and Beavis never collide.

**The record** (schema v2):

```jsonc
{ "schema_version": 2, "source_id": "airhead",
  "tick": 124, "floor": 0, "in_town": true,
  "dsl": "<raw DSL line>",                       // re-parseable → also a parser corpus
  "recommendations": [ {"agent","weight","score","reasoning"} ],
  "commitment": {"incumbent","streak"}, "tactical_mode": "follow",
  "llm": [ {"agent","prompt","response"} ],       // only LLM agents that fired this tick
  "winner": "Movement", "command": "MV 61 69", "repeats": 0 }
```

> Caveat: the trace records the **decision**, not the **outcome** — it won't catch
> "MV target was a wall" or "the cast whiffed." That needs live play. It also
> doesn't capture the emergency-heal hard-override (it `return`s before arbitration).

---

## 2. Analyze — `./dev.sh stats`

```bash
./dev.sh stats                       # all of traces/*.jsonl
./dev.sh stats traces/airhead-*.jsonl   # specific files
```

Per file + an aggregate. How to read each metric:

| Metric            | Means                                              | Smell |
|-------------------|----------------------------------------------------|-------|
| **compression**   | ticks ÷ records. High = a decision held; ~1x = new decision every cycle | **< ~2x = thrashing** |
| **thrash%**       | share of records that held 0 extra cycles          | high = churny |
| **osc**           | A→B→A flip count                                    | the paralysis count |
| **cycle**         | strongest 2-cycle pair (both directions)           | **the ping-pong culprit** |
| **winners**       | who wins, by volume                                | sanity-check the mix |
| **starved**       | agents *recommended* but never winning             | dead agent, or always out-voted |
| **llm**           | LLM calls per agent                                | the real inference cost |

The aggregate `top 2-cycle (ping-pong)` line is usually where the bug is. (On
2026-06-30 it read `Town<->Movement x406` — the follow-flicker, below.)

---

## 3. Replay — pin the cause offline

The powerful move: the `dsl` field re-parses into the exact `state`, and the **16
rule-based agents are deterministic** — feed a recorded line straight back through
an agent and watch what it decides, no game running.

```python
# uv run python - <<'PY'
import json
from dsl_parser import parse_dsl_state
from agents.movement import MovementAgent

recs = [json.loads(l) for l in open("traces/multi_2-20260629-132039.jsonl") if l.strip()]
M = MovementAgent()
for r in recs[38:54]:
    st = parse_dsl_state(r["dsl"])
    resp = M.evaluate(st)
    print(r["tick"], r["winner"], "->", f"{resp.weight:.2f}", resp.reasoning[:48])
# PY
```

This is exactly how the Town↔Movement bug was nailed: replaying the recorded state
showed she had **6 potions** (no errand) and Movement's follow weight flipped
0.2↔0.7 on a one-tile drift — a missing hysteresis band, invisible from the live
record's "going to Pepin" reasoning string. Run it under `uv run python` so the
venv (`requests`) is present.

> LLM agents (combat/chat/shopping/griswold/adria) aren't deterministic — but
> their `(prompt, response)` is in the record's `llm[]`, so a replay harness can
> stub `query_llm` from it. Rule-based agents need nothing.

---

## 4. Live — `M-x gap-hud`

`HUD=1 ./launch_agent.sh`, then `M-x gap-hud` in Emacs (`gap-hud.el`). It polls
`.hud/<hero>.json` and renders the live council — recommendations, scores, winner,
commitment — i.e. the latest trace record, rendered. Best tool for *watching*
paralysis happen; `./dev.sh stats` is for *quantifying* it after.

---

## The worked loop (2026-06-30)

1. `./dev.sh stats` → aggregate `Town<->Movement x406`, town compression 1.2–1.6x.
2. Replay the worst file → she has 6 potions; Movement flips 0.2↔0.7 at a 1-tile
   boundary → 2-tile limit cycle next to Pepin.
3. Fix: follow **hysteresis** (START=5 / STOP=2 held stance) in `movement.py`.
4. Re-replay the same window → 8 winner-flips → **0**. (Then live-test + re-`stats`
   to confirm in-game.)

Kill a planned task, pin the true bug — both from the corpus. That's the point.

---

See also: `decision_tracer.py` (the sinks), `trace_stats.py` (the analyzer),
`gap-hud.el` (the live reader), ROADMAP.md → **Track E** (the why).
