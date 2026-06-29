# GAP HUD — Design Doc

> **Status:** P0–P3 **implemented** 2026-06-29 (headless-tested; not yet validated
> against a live game session). Supersedes the `hud-idea.md` brainstorm.
> **One line:** an Emacs cockpit that renders the council's decisions live, by
> reading the *same* record the decision tracer already produces.
>
> **What landed:** engine `N=` hero name in the DSL; `source_id` threaded through
> records, logs (toon-prefixed), and the live envelope; `build_decision_record`
> + sink fan-out; `LiveSink` (`--hud`/`HUD=1`) writing an atomic envelope;
> LLM model/token/latency capture (schema **v2**); `gap-hud.el` v1 (buffer+timer).
> **Remaining:** P4 replay/history navigation, P5 child-frame overlay, and a live
> in-game smoke test (3-terminal loop with `HUD=1` + `M-x gap-hud`).

## Thesis

The HUD is **not a new subsystem** — it's a second *reader* of an artifact GAP
already emits. `decision_tracer.py` (Track E) records one structured object per
`decide()`. That object already carries almost everything `hud-idea.md` wants on
screen. So the work is not "build a telemetry pipeline"; it's "fan the existing
record out to a live sink, and add an Emacs renderer."

This is the talk-idea.md philosophy made literal: *the AI runtime is an
observable subsystem.* Observability is not demo polish bolted on the side — it
is another consumer of the recorder that already feeds replay and CI. One record
schema; one renderer; three sources (live / recorded / replay).

```
                          ┌──────────────────────┐
   decide() ──record──▶   │  decision record     │   (the existing dict built
                          │  (already built)     │    at orchestrator.py:909)
                          └──────────┬───────────┘
                       fan-out to N sinks (new: ~15 lines)
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                       ▼
     DecisionTracer (sink #1)  LiveSink (sink #2, new)  (future) socket
     traces/*.jsonl            .hud/latest.json         for remote/web
     deduped, durable          un-deduped, last-write
     → replay / CI / B5        → Emacs tails this
              │                      │
              ▼                      ▼
        ┌─────────────────────────────────────────────┐
        │  ONE Emacs renderer, THREE sources:          │
        │   • live   — poll .hud/latest.json           │
        │   • replay — scrub a traces/*.jsonl session  │
        │   • test   — render replay-harness diffs     │
        └─────────────────────────────────────────────┘
```

## What the record already gives us (no new capture)

From `decision_tracer.record(...)` (orchestrator.py:909) every record has:

| HUD panel (hud-idea.md)                      | Field on the record                                           | Source            |
|----------------------------------------------|---------------------------------------------------------------|-------------------|
| Recommendations + scores (`HazardAgent 9.2`) | `recommendations[]` (`agent`, `weight`, `score`, `reasoning`) | council vote      |
| Winner + command                             | `winner`, `command`                                           | arbitration       |
| Intent / goal / lease                        | `commitment` (`incumbent`, `streak`), `tactical_mode`         | CommitmentTracker |
| "Because…" reasoning                         | per-agent `reasoning` + `llm[].response`                      | agents            |
| Party HP/MP, target, world facts (fire/loot) | raw `dsl` line → parse with `dsl_parser.py`                   | engine            |
| Churn (how stuck she is)                     | `repeats` (dedup count)                                       | tracer            |

That table is the demo. The killer panel from talk-idea.md —

```
HazardAgent      score 9.2
LootAgent        score 4.1
MovementAgent    score 3.7
Winner: HazardAgent   Reason: Standing in fire.
```

— is a direct render of `recommendations[]` sorted by `score`, plus `winner` and
its `reasoning`. No new data needed.

## The one capture gap: LLM plumbing

The "model / tokens / latency / prompt size" panel is the only thing the record
can't fill today. `BaseAgent._trace_llm` (base.py:149) captures `prompt` and
`response` text but drops the rest. The fix is localized and *single-point*:
`query_llm` already holds `resp.json()`, and Ollama's response includes
`eval_count`, `prompt_eval_count`, and `*_duration` nanosecond timers. Enrich the
sink payload at that one call site:

```python
# base.py query_llm, after resp.json()
j = resp.json()
self._trace_llm(full_prompt, response_text, meta={
    "model": self.model,
    "prompt_tokens": j.get("prompt_eval_count"),
    "out_tokens": j.get("eval_count"),
    "latency_ms": round((j.get("eval_duration", 0)
                         + j.get("prompt_eval_duration", 0)) / 1e6),
})
```

This is useful **beyond the HUD** — latency/token counts belong in the durable
corpus anyway (cost/perf regressions become as measurable as decision churn).
Bump `SCHEMA_VERSION` to 2 when `llm[]` entries grow these keys; old v1 traces
still parse (the renderer treats the keys as optional).

## The one design subtlety: dedup vs. live

`DecisionTracer` is **log-on-change** — it holds the in-flight record and only
flushes when the decision *meaningfully changes*, folding identical re-decisions
into `repeats`. That is correct and load-bearing for B5 (churn is the metric).
But it means a live HUD tailing `traces/*.jsonl` would **lag by one decision** and
miss every tick where nothing changed.

So the HUD must **not** tail the durable trace. Instead, fan the record out:

- **Sink #1 — `DecisionTracer`**: unchanged. Durable, deduped, feeds replay/CI.
- **Sink #2 — `LiveSink` (new, ~20 lines)**: writes the *current* record to
  `.hud/<source>.json` every tick via atomic write (`os.replace` of a temp file),
  no dedup, last-write-wins. The HUD polls this one file.

### Identity & envelope (decided up front, not retrofitted)

Two fields go in from day one so multi-client and schema evolution never need a
migration:

- **`schema_version`** — already on every record (now `2`, see below). The
  renderer branches on it; a v1 corpus stays recognizable.
- **`source_id`** — which client produced this (`multi_1`, later a persona like
  `airhead`/`beavis`). Derived from the socket stem at construction, overridable.
  Without it, the Airhead+Beavis coordination demo can't tell two feeds apart.

`LiveSink` does **not** write a bare record — it writes a small **envelope** so
Emacs can detect staleness/offline and attribute the feed without trusting file
mtime:

```json
{
  "schema_version": 2,
  "source_id": "airhead",
  "written_at": "2026-06-29T18:22:04.511Z",
  "offline": false,
  "record": { "...": "the existing decision record" }
}
```

On clean shutdown `LiveSink.close()` rewrites the envelope with
`"offline": true` (record retained) so the cockpit shows a definitive OFFLINE
rather than a frozen-but-maybe-live panel. `schema_version` is mirrored to the
envelope top so the HUD can read it without descending into `record`.

Refactor the single `if self.tracer:` block (orchestrator.py:909) into:

```python
record = build_decision_record(...)   # the dict, factored out once
for sink in self.telemetry_sinks:     # [tracer?, live_sink?]
    sink.offer(record)
```

Both sinks share one `build_decision_record`; neither knows about the other. A
future remote/web sink is a third entry in the list — the philosophy holds.

## Emacs renderer

### Why not ytr
`xenodium/ytr` is a YouTube *audio* player, not a HUD framework — the link in
`hud-idea.md` points at the *technique*, not reusable code. What's worth copying
is his use of an Emacs **child frame** (floating frame) for a graphical overlay.
Defer that; it's fiddly. Start with a plain buffer.

### v1 — buffer + timer (~150 lines elisp, low risk)
`gap-hud.el`: a `gap-hud-mode` buffer and a 500 ms `run-with-timer` that re-reads
`.hud/latest.json`, parses it (`json-parse-buffer`), and renders sections:

```
  Airhead   floor 3   tick 12480   stance: ENGAGE   (committed: Combat ×7)
  ─────────────────────────────────────────────────────────────────────
  COUNCIL                                   LLM
   Combat      9.2  ████████  attack pack    qwen2.5:3b
   Loot        4.1  ███       grab ring       142 tok in / 18 out  · 310 ms
   Movement    3.7  ██        follow
  WINNER  Combat → AT 27        because: 4 clustered, ally safe
  ─────────────────────────────────────────────────────────────────────
  PARTY  HP 72%  MP 33%   target M12@38,16   |   churn ×3
```

This alone is demo-grade: scores update live next to the running game. No new
Emacs deps (`json-parse-buffer` is built in). Bind a toggle, drop it in a side
window next to the DevilutionX frame and Magit.

### Install — it stays in *this* repo
`gap-hud.el` deliberately lives in `tools/gap/`, **not** in personal Emacs config.
It renders the orchestrator's record, so it must version lockstep with that
schema — vendoring a copy into `~/.emacs.d` would let the two drift. It is fully
standalone (built-ins only: `json`, `time-date`, `seq`) and **self-locating**: it
resolves the repo's `.hud/` dir relative to its own file (`gap-hud--dir` captured
from `load-file-name`), so the default feed path is correct no matter where Emacs
is when it loads. Three tiers (full detail in the file's Commentary header):

1. **Try it:** `M-x load-file RET tools/gap/gap-hud.el RET` → `M-x gap-hud`.
2. **Adopt (straight + use-package):** point at the repo, don't let straight
   manage it —
   ```elisp
   (use-package gap-hud
     :straight nil
     :load-path "~/Projects/DevilutionX/tools/gap"
     :commands (gap-hud gap-hud-stop))
   ```
   (matches the existing `:straight nil` local-package idiom in jps-emacs.)
3. **Plain Emacs:** `add-to-list 'load-path` + `autoload`.

`M-x gap-hud` auto-finds the default hero's feed; `C-u M-x gap-hud` prompts and
defaults to the most-recently-written `.hud/*.json` (so Beavis is one keystroke
away from Airhead). Run the agent with `HUD=1 ./launch_agent.sh` to produce the
feed.

### v2 — child-frame overlay (polish, deferred)
Once v1 proves the data flow, lift the same render function into a child frame
(ytr-style) so it floats as a true cockpit overlay for recording the demo. Same
renderer, different container.

### Replay / history viewer (mostly free once v1 exists)
Point the *same* render function at a recorded `traces/*.jsonl` instead of
`latest.json`, plus prev/next-decision navigation (`n`/`p` step records, render
each). This is the "scrub the decision trace" capability from talk-idea.md —
"you can literally replay the decision." `repeats` shows how long each decision
held. Test/diff view: render the replay-harness output (expected vs. actual
winner) with the mismatch highlighted.

## Why this is the right shape

- **No data model invented** — the HUD reuses the Track E schema. If the schema
  evolves, the HUD and CI evolve together.
- **The "suite of tools" is one viewer** — live, history, and replay are the same
  renderer pointed at different byte streams. That is the "streams of bytes and
  library code" intuition, made concrete.
- **Sinks compose** — durable corpus and live feed never interfere; a remote sink
  is a future list entry, not a rewrite.
- **Risk is isolated to elisp polish**, which is deferrable (v1 buffer is trivial;
  child frame is optional).

## Phasing & effort

| Phase | Work                                                                            | Effort | Risk                      | Status  |
|-------|---------------------------------------------------------------------------------|--------|---------------------------|---------|
| P0    | Engine `N=` hero name in DSL; parser; `source_id` + toon-prefixed logs          | ~2 hrs | low                       | ✅ done |
| P1    | Factor `build_decision_record`; sink fan-out; `LiveSink` → `.hud/<source>.json` | ~½ day | low, additive             | ✅ done |
| P2    | LLM-plumbing capture (model/tokens/latency) in `query_llm`; schema v2           | ~2 hrs | low                       | ✅ done |
| P3    | `gap-hud.el` v1 (buffer + timer, live) + `HUD=1` launch wiring                  | ~½ day | low (elisp)               | ✅ done |
| P4    | Replay/history navigation in the same renderer                                  | ~¼ day | low                       | todo    |
| P5    | Child-frame overlay (demo polish)                                               | ~1 day | med (child frames fiddly) | todo    |

P1–P3 is the minimum that yields the "scores updating beside the running game"
demo. P4 unlocks "replay any past decision." P5 is for the recorded talk.

## Open questions

1. **Live cadence** — write `latest.json` every tick, or throttle to ~5 Hz? Every
   tick is simplest and the file is tiny; throttle only if disk churn shows up.
2. **`.hud/` location** — sibling of `traces/` (git-ignored), or under the
   scratch dir? Leaning `tools/gap/.hud/` next to `traces/`, cleaned by
   `dev.sh clean`.
3. **Live transport** — file poll (chosen: zero deps, survives restarts, trivial)
   vs. a socket the HUD connects to (lower latency, but adds a server). File wins
   for v1; socket can be a later sink if 5 Hz polling ever feels laggy.
4. **Multi-agent** — with Airhead *and* Beavis as separate clients (talk-idea.md
   coordination demo), each headless client writes its own `latest.json`; the HUD
   shows N panels. The sink design already supports this (per-process file).

