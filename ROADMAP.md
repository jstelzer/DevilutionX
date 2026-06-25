# GAP Roadmap — after true-MP + multiple AI clients

The framework is done. The AI is a true second player; multiple AI clients work
(Rogue + Sorc as players 2 & 3, 2026-06-23). Everything below was *postponed
until we had a working framework* — it's the backlog, not bugs.

---

## 🟢 SESSION HANDOFF — 2026-06-23 PM (read this first)

**Sorcerer casting works now.** She threw Firebolts at the Butcher from range
(verified: `Successfully queued spell 1 type 1`). Getting there took fixing a
*chain* of bugs — DON'T reintroduce any of these:
- **`KS=`/`RS=` were emitted only inside `if(DTYPE_TOWN)`** in `gap_dsl.cpp` →
  `state["spells"]` was empty underground (`nspells=0`) → caster meleed. Now
  emitted unconditionally (must stay outside the town block).
- **Spell-id bitmask is `1<<(id-1)`** (`GetSpellBitmask`), not `1<<id`. The KS
  encoder must test `known & GetSpellBitmask(sid)`, not `(known>>s)&1`.
- **`spell.py` ids must be real `SpellID` enum values** (Firebolt=1, Lightning=3,
  Fireball=12, ChargedBolt=30, TownPortal=7…). The old 2/15/16 values were wrong.
- **`ExecuteCastSpell` picks the source** (mem→Spell / staff→Charges / scroll /
  ability) and sends **`CMD_SPELLXY` as Param3** `(id,type,spellFrom=0)` — NOT
  Param4 (level goes in spellFrom slot → rejected). `GetManaAmount` is fixed-point.
- **SpellAgent targets ANY visible mob**, not just `flags&1` (hostile is only set
  when goal==Attack; approaching/human-targeting mobs read as non-hostile).
- **left-click = attack (`AT`), right-click = cast (`CAST`→CMD_SPELLXY)** — the two
  paths are distinct; don't cross them.

**Pending live-test (Python-only, just need an agent restart):**
- cast-kite (caster MVs toward a mob >15 tiles to close into cast range),
- belt-refill give-up (stop looping on an unbeltable scroll/book),
- town restock-stickiness (low HP-pots in town → Pepin trip beats follow),
- inventory-drink heal (`UI <slot>`), faster cast cadence (cooldown 5).

**Known-good run flow** (host must be IN the game world, not the menu, or joins
get connection-refused): start each client, **wait for "headless joined as player
N"** before launching its agent. Launch steps must be SEPARATE bash calls — a
`pkill` in the same command as a launch races and kills the new client. There are
**12 unpushed commits** on `GAP`.

**Still-open / next:** push GAP; strip the temp `inv=`/`wpn=` debug from the
orchestrator state log; cleaner C++ "beltable" flag (like the loot `fits` flag);
the Rogue makes ~1200 Loot decisions *in town* (item churn — investigate);
cast-range cast-kite could place at range instead of walking onto the mob.

---

## The model: two tracks (this is the whole point)

Remaining work splits cleanly, and the split decides where formal modeling helps.

|                 | **Track A — Capabilities**                                       | **Track B — Coordination**                           |
|---------------|----------------------------------------------------------------------------|---------------------------------------------------------------------|
| What        | One agent doesn't know / can't use a game mechanic | Invariants *across* multiple players/agents          |
| Nature      | Local, deterministic, single-client                               | Concurrent, racy, hard to reproduce live             |
| Examples | doors, altars, spells, scrolls, mana                              | loot ownership, portal ownership, stance arbitration |
| TLA+?      | **No** — just build + live-test                                    | **Yes** — but just-in-time, scoped per feature       |

**TLA+ stance:** defer the broad model (the protocol is still growing — a spec
would rot). Write a *small* spec **immediately before** each Track B feature, not
a big upfront pass. We just crossed N≥2 agents, so these bugs are now real (the
pickup grant-race was a preview). First candidate spec: **item ownership** (below).

---

## Track A — Capabilities (build now, no TLA+)

### A1. World interaction — doors, altars, chests, barrels, shrines, fountains
- The DSL **already emits `OBJ=`** (e.g. a door shows as `OBJ=113@25,36,dr`), and
  an `exploration.py` agent exists — so this is partly scaffolded.
- Gaps: (a) an **operate/interact command** in the DSL + C++ executor; (b) the
  agent **knowing what each object is** and whether it's worth/safe to use;
  (c) **safety gating** (don't pop a chest with 5 mobs adjacent).
- **Key unlock:** the old `if (&player != MyPlayer) return;` guards that blocked
  *companions* from shrines/fountains/barrels (see `Source/objects.cpp`,
  CLAUDE.md "Known Restrictions") are now **moot** — the AI *is* `MyPlayer` in its
  own client. So most object interaction should "just work" once the command +
  agent policy exist. Verify this assumption early.
- Open questions to decide per object: shrines (many have downsides — opt in?),
  fountains (resource limit?), barrels (break for loot/spawns?).

### A2. Action system — 🟡 MOSTLY DONE (2026-06-23)
The principle that emerged: **the engine owns the metadata; the DSL publishes it;
Python only does tactics.** No parallel id/name/mana tables (those drifted into
the `FIREBOLT=2`=Healing bug).
- ✅ **Self-describing spell menu in the DSL** (`KS=id,name,lvl,mana,flags` +
  `RS=id` readied), sourced from `_pMemSpells|_pAblSpells` + `GetSpellData` +
  `GetManaAmount`. Includes the class skill (Warrior Repair) and exact mana cost;
  per-client (only her own spells).
- ✅ **Selection policy:** SpellAgent casts only known/affordable/offensive spells
  (strongest affordable; AoE for clusters), referenced by engine name. Activation
  is "knows an offensive spell or has staff charges" — not a Magic-stat guess.
- ✅ **Mana awareness:** ManaAgent drinks mana potions when a caster runs low.
- ✅ **Staff charges:** parsed (`st^charges:spellID`) and preferred to save mana.
- ⏳ **Use the readied default action / class skills** (e.g. auto-Repair via the
  Warrior skill instead of a Griswold trip; Rogue Disarm on traps). `RS=` is now
  exposed — wire agents to it.
- ⏳ **Offensive scroll use** (cast attack scrolls from belt/inventory) — the
  scroll codes are in the DSL; no agent fires them yet.

### A3. Inventory lifecycle — ✅ DONE (2026-06-23)
- ✅ **Make room before grabbing:** LootAgent drops the least-valuable junk when
  the pack is full so a magic/unique find isn't left behind.
- ✅ **Sell-loot:** GriswoldAgent already sells identified junk in town (one/tick).
  The only un-closed bit is *returning* to town when full — see B4 economic
  extraction below.
- ✅ **Cain multi-item ID:** deterministic, class-appropriate first (loops the
  whole pack over ticks).
- ✅ **Mark old gear for sale:** GriswoldAgent sells redundant gear (worse than
  what's equipped) via ItemComparator.find_redundant — the downgrade left after
  an upgrade no longer piles up.

### A4. Hazard awareness — "see the fire" — 🟢 MOSTLY DONE (2026-06-24)
Before this she couldn't perceive ground hazards at all: the DSL emitted monsters/
loot/objects but **no danger layer**, so standing in a Fire Wall / Inferno /
incoming AoE was an *invisible* threat and she'd attack from inside it.
- ✅ **Hazard layer in the DSL** (`HZ=x,y,kind;...`): hostile missiles/AoE near
  her, sourced from the live `Missiles` list exactly like `TP=` portals. Only
  `TARGET_PLAYERS`/`TARGET_BOTH` missiles count, so it never flags her own or the
  human's offensive spells. `kind` = damage element (fire/lght/acid/arc/phys) via
  `GetMissileData`, so Track D can scale per-element tolerance. Emitted
  unconditionally (not town-gated — the `KS=` bug-chain lesson).
- ✅ **Parser + helpers:** `state["hazards"]` in `dsl_parser.py`; `hazards.py`
  (`is_tile_dangerous` / `nearest_safe_tile`, Chebyshev, safe-tile search biased
  toward the player so she dodges *toward the party*).
- ✅ **Use it — `HazardAgent`:** rule-based "step out of the fire" reflex at
  priority 10 (matches critical healing). Strong when ON a hazard, weaker when
  adjacent, damped by a `_fire_tolerance` hook (defaults low; the D1 slider wires
  in later). Hazards also fold into `_compute_danger` so loot/exploration/movement
  dampen near fire. Helps every class regardless of personality.
- ⏳ **v2 — hazard terrain:** lava / hazard tiles via terrain flags (v1 is
  missiles only; `gap_dsl.cpp` has a comment marking the spot).
- ⏳ **Live-test (Step 4):** Sorc vs a fire-thrower — confirm `HZ=` shows in the
  state log and she steps off the burning tile. The C++/parser/agent all build +
  unit-test clean; only the in-game confirmation is outstanding.
- This is the gate for Track D's *fire tolerance* — the `_fire_tolerance` hook is
  already in `HazardAgent`, waiting for D1 to drive it.

---

## Track B — Coordination (write a small TLA+ spec just before each)

These are the party-protocol invariants. Each gets a scoped spec, then the build.

### B1. Item / loot ownership across agents — lighter than it looks (B5 leads now)
With 2 AIs + you, who claims a drop? **Key realization: the engine already
resolves hard contention** — if two players rush an item, whoever clicks first
wins and the other gets *nothing*. So "no duplicated ownership" isn't ours to
guarantee; the engine enforces it. That collapses B1 from an ownership protocol
down to two soft concerns: **oscillation** (A and B don't both walk to the same
item forever) and **efficiency** (don't send two agents after one drop when the
loser will arrive to an empty tile). We already hardened single-item pickup (the
`_iRequest` debounce). With the hard invariant handled by the engine and the soft
parts cheap, B1 **slides behind B5** — and once leases exist, "claim a drop" is
just a short-lived lease, so B1 largely *falls out* of B5 rather than needing its
own protocol.

- **Town trade flow (social, depends on the loot/sell path):** before Griswold
  sells a keepable-but-unwanted item, broadcast *"anyone want this before I sell
  it? `<item>`"* → if someone says yes, `DROP` it for them; if not (or after a
  short timeout), sell. Reuses the chat path + the existing recently-dropped
  anti-pickup blacklist. Turns her pack into a party resource instead of vendor
  fodder — characterful, and a natural fit once Phase 0 makes selling deterministic.

### B2. Portal & level ownership — no stranding
Invariants: portal ownership is unambiguous; using a portal never strands a party
member; party reunification is always possible; transition state can't get stuck.

### B3. Stance arbitration
Invariants: **RETREAT dominates ENGAGE**; an agent **always has ≥1 legal action**;
support actions can't violate survival constraints; role assignment can't become
contradictory. (Stances exist — HOLD/ENGAGE/RETREAT/FOLLOW — but the guarantees
aren't formalized.)

### B4. Adria / portal *production* (consumer → producer) — 🟡 PARTIAL (2026-06-23)
The step from *using* your portals to *making* its own:
```
need extraction → can I create a portal? → have the resource? → place it → coordinate party
```
- ✅ **Survival extraction, scroll provider:** ExtractionAgent opens her own town
  portal from a scroll (`sp`, via `CS`) and steps to town when doomed (low HP, no
  healing, no human portal). Pure Python — DSL already exposed the pieces.
  Honors ownership / no-stranding / liveness / no-yo-yo invariants (documented in
  the agent).
- ✅ **Spell provider:** casts Town Portal directly when known + affordable,
  found by name from the engine spell menu (A2). Scroll preferred (saves mana).
- ⏳ **Economic extraction:** open a portal to go *sell* when the pack is full
  (closes the sustained-run loop), and the **return trip** back to the dungeon.
- ⏳ **Invite the human through her portal:** needs the go-first/hold dance
  PortalAgent already does for the consumer side.

Designed as a reusable **PortalCapability** (provider-pluggable), not Rogue/Sorc-
specific. The spell provider and economic/return legs depend on A2 (action
system) and B2 (portal ownership).

### B5. Intent leases — stop re-electing a decision that's already made ← strong candidate spec
**The friction:** "walking across town to sell shit shouldn't revalidate so
much." Right — *walking to Griswold* isn't a decision, it's the **execution** of
one, and the council re-runs the whole election every `think_interval` (0.6s)
anyway. Walking isn't deliberation; the skeleton is the cache-bust.

**The cost is real and it's LLM inference, not Python.** Of 22 agents, 16 are
rule-based (microseconds); only 6 hit the LLM (`combat`, `chat`, `shopping`,
`griswold`, `adria`). In town with sellable junk, `griswold.should_activate()`
is True every tick → `query_llm` every 0.6s, plus `shopping`/`adria` — ~2-3
redundant inferences/sec re-deciding "should I sell?" when she's already walking
there. A Rust rewrite makes redundant inference *faster*; a lease *removes* it.
That's the bigger win.

**We already have a half-lease, and it runs too late.** `CommitmentTracker`
(orchestrator.py) gives the incumbent goal a +2.5 score bonus with streak decay —
but it's applied *after* every agent has already run `evaluate()` (and burned its
LLM call). So it fixes goal **oscillation**, not churn **cost**. The lease is that
same idea promoted from "bias the score post-hoc" to "skip re-evaluation while
valid." It's an **invalidation model, not a timer**: the lease holds until reality
changes (enemy enters awareness, target dies, HP threshold crossed, loot of
interest, stance change, level transition, path stuck; in town: player command,
inventory/gold change, vendor done, portal appears).

**Design constraints (learned, not in the original sketch):**
- **The hard part is the invalidation set, not issuing the lease.** Miss a bust
  event and the failure flips from *annoying churn* to *dangerous
  unresponsiveness* (keeps walking while a skeleton eats her). Keep a **timeout
  backstop** even though it's "not a timer" — the liveness clause itself says a
  lease eventually *expires*. Belt and suspenders.
- **Reflexes are never leased.** The priority-10 survival agents (Hazard, critical
  Healing, player Chat, Extraction) are exactly the *invalidation sources*. The
  tiers already encode the line: **≥8 always evaluates and can preempt; ≤7 is
  leaseable** (sell/buy/explore/follow/upgrade). Two-tier with almost no new
  concept. NB: in **town** there are no monsters, so leased town goals have a
  tiny, safe bust set (player command / inventory / vendor-done / portal) — the
  unresponsiveness risk is a *dungeon* concern, which makes Phase 0 low-risk.
- **A lease is a held stance.** Same preemption machinery as **B3 stance
  arbitration** ("RETREAT dominates ENGAGE", "always ≥1 legal action"). Design
  them together so we don't build two preemption systems.
- **Observability is a first-class requirement, not a nicety.** Surface the live
  lease — name, age, why it was acquired, its invalidation set, and state:
  ```
  Lease: SELL_JUNK   age: 7.4s   reason: inventory full
  invalidation: enemy | player command | vendor complete
  state: executing
  ```
  The first time she walks past three monsters because a bust event wasn't wired,
  this tells you *why* at a glance — and watching her current commitment live
  makes for a far better demo than a log tail. Log it on lease change + on bust.

**Sequencing (cheap first — measure before abstracting):**
- **Phase 0 (now, cheap):** the vendor LLM calls are *decorative* — `griswold`'s
  `_sellable_items()` already computes the plan in pure Python; the LLM after it
  decides nothing. Make Griswold/Shopping/Adria rule-based (or cache the command,
  re-query only on inventory/gold/threat change). Probably removes most of the
  observed friction with **no new primitive**. Low-risk in town (no reflexes fire).
- **Phase 1:** promote `CommitmentTracker` → real lease: incumbent holds a lease
  with an explicit invalidation predicate; council skips re-scoring leaseable
  agents while valid; survival tier always evaluates and can bust it; timeout
  backstop.
- **Phase 2:** move long-running tactics (vendor sequences, path-to, portal/
  transition) *under* the lease so they own retries / stuck-detection — the
  "tactics = execution engine" payoff (the roadmap's "longer-running tactics with
  richer history").
- **Phase 3 (Track B spec):** TLA+ the invariants once stance-preemption (B3)
  interacts with leases. *Safety:* an agent holds **at most one** active lease.
  *Liveness:* a lease eventually **completes / expires / is interrupted**. This is
  a *single-agent* spec — simpler than B1 loot-ownership and high-value, so it may
  be the first Track B spec worth writing.

---

## Track D — Character (personality & relationship)

The layer that turns a competent bot into someone you tell stories about. The
goal isn't a flawless tactical machine — it's a companion that gets it *wrong*
in characterful, bounded ways. Players don't remember the clean runs; they
remember "that time the rogue opened every barrel while Diablo was punching us."

### D1. Personality sliders
Per-character traits in `[0,1]` that bias the council's agent weights at
`decide()` time (the council already scores `weight × priority`; sliders are just
per-agent multipliers — the explicit version of the learning-loop nudge and
`_combat_confidence_mult` we already have):

| Slider | Scales |
|---|---|
| **Greed** | Loot/Upgrade weight, make-room aggressiveness, breaking off a fight for a shiny |
| **Curiosity** | Exploration (barrels/chests/doors/shrines), wander-vs-follow |
| **Obedience** | How hard a chat stance (HOLD/ENGAGE/RETREAT/FOLLOW) overrides her own judgment |
| **Discipline** | Self-preservation: heal/extract thresholds, holding formation, **fire tolerance** (A4) |

**Bounded imperfection is the whole point:** sliders bias *preferences*, but hard
survival floors stay (emergency reflexes + a Discipline floor) so it reads as
"yep, that's one of us," not "decorative houseplant." Low Discipline + high
Greed/Curiosity = lingers in the fire "for science"; high Discipline = already at
the rally point. Same engine, two personalities. Lives in `PersonalityStore`
(traits + confidence already exist).

### D2. Relationship-driven adaptation (emergent)
Sliders aren't only authored or self-taught from deaths — they **adapt to THIS
player**, via the memory system (`PersonalityStore` already records memories with
emotional impact + a `player_relationship` trait):
- **Observe the player:** do they share (drop potions/gold for her, help when
  she's low, wait up) or hoard (grab every drop, leave her behind, let her die)?
- **React over time:** a generous player earns loyalty → Obedience/▼Greed (she
  shares back, sticks close); a greedy/abandoning player → ▲Greed/▼Obedience
  (she looks out for herself, races you to drops). Recorded as memories, surfaced
  in chat ("you always have my back" vs "last time I went down you kept walking").
- Emergent: the same hero develops a different personality depending on who she
  adventures with. That's the payoff.

Depends on A4 (so "fire tolerance" means something) and a stable council
(weights are the tuning surface).

---

## Track C — Cleanup (whenever)
- Remove inert sidecar dead code: `gGapCompanionSlot` across `multi.cpp`/`pfile.cpp`,
  and `Source/seat/` (already `!gGapHeadless`-gated, safe to delete carefully).
- Strip leftover debug `SDL_Log`/`std::cerr` markers; make `ENABLE_GAP` global.
- Push `GAP` (well ahead of origin) when ready.

---

## Track E — Decision tracing & offline testing (🟢 CORE INFRASTRUCTURE)
> Promoted from "auxiliary feature" to **core infrastructure** (2026-06-25). It's
> the flight recorder the whole ecosystem reads from: B5 becomes measurable,
> weight tuning goes offline, regressions become CI failures, TLA+ invariants get
> grounded in observed behavior instead of speculation, and any future rewrite has
> a behavioral oracle. The kind of thing that pays dividends for years — so build
> it like infra (versioned schema, sane volume), not a debug `print`.

**Principle it makes explicit — the engine owns outcomes, the council owns
decisions.** Two different systems. Track E tests/observes the decision system; it
deliberately says nothing about whether the decision *worked* in the world. Keep
that boundary clean (it's why the caveat below is honest, not a weakness).

**The unlock:** `decide()` is almost a pure function `state → command` — the only
impurity is internal council state (CommitmentTracker incumbent/streak,
tactical_mode), which we can log too. **Record the decision stream as JSONL and we
can replay the council offline forever** — write tests for weights/priority and
simulate `decide()` without playing level 1 a billion times. Behavior tests and
class profiles become automatable.

**The implementation is tiny.** At the selection point (`orchestrator.py`, where
`best = max(recommendations, …)`) everything is already in scope: the full
`recommendations` list `(agent, weight, score, reasoning)`, the winner, the
command, commitment state, tactical_mode, and the raw state. A `--trace PATH` flag
+ one JSONL append per decision. Reuse the `prepare_companion_state_for_db`/
`llm_view` serialization precedent.

**The test surface splits in two — the same line as B5's tiers:**
1. **Arbitration (deterministic, testable today, zero mocking):** given a recorded
   `recommendations` set → assert the winner. Tests scoring × priority ×
   commitment math directly, no LLM, no engine. The 80% win, and pure.
2. **Agent decisions:** the **16 rule-based agents** (Hazard/Healing/Loot/Movement/…)
   replay deterministically from recorded `state` — direct unit tests, no mocking.
   The **6 LLM agents** (combat/chat/shopping/griswold/adria + base) need their
   `(prompt, response)` recorded so replay can stub `query_llm`. **Bake that into
   the schema from day one** or the corpus can't reproduce LLM-driven decisions.

**Suggested record schema (one JSON object per decision):**
```
{ schema_version: 1,              # it's a contract now — a v1 corpus must still
  tick, floor, in_town,           #   replay against a future decide(); version it
  dsl: "<raw DSL line>",          # re-parseable → also a parser regression corpus
  recommendations: [ {agent, weight, priority, score, reasoning} ],
  commitment: {incumbent, streak}, tactical_mode,
  llm: [ {agent, prompt, response} ],   # only the LLM agents that fired this tick
  winner, command }
```

**What it buys:**
- **Flight recorder (single-incident postmortem — the day-to-day win):** when she
  does something dumb at tick 14892, read the one record and see *why* — full
  recommendation set, scores, commitment state. "Hazard layer was empty so Loot
  won" vs "hazard layer wasn't empty and the lease wasn't busted → bug" are two
  completely different debugging sessions, and the trace tells you which in one
  glance instead of "huh…".
- **Counterfactual replay:** re-run a recorded session with one knob moved (`Loot
  +10%`) and diff — *which* decisions changed, and *where*. The diff is the signal.
  (Honest limit: it tells you which decisions **change**, never which are
  **better** — "better" needs a label or an outcome proxy, and outcomes live in
  the engine, not the trace. Track E makes tuning offline and observable, not
  automatic; a human or a labeled subset still closes the loop.)
- **Regression/golden tests:** freeze decide() on a corpus; a weight tweak that
  silently breaks combat fails CI instead of being found mid-run.
- **Behavior/profile tests:** assert archetypes from recorded *or synthetic* states
  (Warrior rushes, Rogue kites, Sorc casts, anyone steps out of fire).
- **Pathology mining → assertions:** oscillation (winner flips N× in M ticks),
  churn (same winner re-deciding an unchanged state — the B5 smell), starvation
  (an agent that should win never does).
- **Behavioral oracle for any rewrite:** if GAP is ever ported (the morning's Rust
  urge), the trace corpus is the pin — the new impl must reproduce the old
  decisions before it earns trust.

**Design notes (build it like infra):**
- **Versioned schema:** a `schema_version` field + keep `decide()` replayable
  against old records, or every refactor invalidates the corpus. Cheap on day one,
  expensive to retrofit.
- **Log on change, not every tick:** ~6k records/hour, mostly identical re-decisions
  while walking. Emit on decision/state change → smaller *and* denser corpus, and
  the dedup ratio itself is a churn metric (it literally measures the B5 problem).

**Synergies (this is infrastructure, not a feature):**
- It **is** B5's observability substrate — the live-lease readout is just the
  latest trace record rendered.
- It's how we **measure B5 Phase 0** ("did rule-based vendors kill the churn?") —
  diff trace stats before/after instead of guessing. So Track E lands *before*
  B5 Phase 0.
- **Evidence-driven invariants (Track E → Track B):** mine the corpus for
  pathologies *first*, then promote the recurring ones to TLA+ invariants — specs
  written from observed behavior, not intuition. This is how Track B specs should
  get written here: the trace tells you what's actually breaking before you spend
  a spec on it.

**Caveat (scope honestly):** the trace tests the *decision*, not the *outcome* —
it won't catch "MV target was a wall" or "the cast whiffed". That still needs live
play or an engine sim. But decision-correctness is most of the tuning pain.

---

## Progress (2026-06-24)
Done this run: **A4 hazard awareness** ✅ emit→parse→agent (`HZ=` danger layer,
`HazardAgent` dodge reflex at priority 10, danger-fold) — live-test (Step 4) and
v2 terrain hazards still pending. Also: loot never scavenges in town (item-churn
fix). Fresh-install dep gotcha: only `sdl2_image` was missing (`pacman -S
sdl2_image`); rebuild via `ninja -C build devilutionx` (cmake not on PATH but
self-invokes).

## Progress (2026-06-23)
Done this run: A2 mana awareness ✅, Sorc ranged casting ✅, A1 doors ✅,
A3 inventory lifecycle ✅ (make-room, redundant-sell, Cain multi-ID),
B4 survival extraction ✅ (scroll + spell providers),
A2 action system ✅ (self-describing spell menu; spell-id bug fixed).

## Suggested sequence (remaining)
1. **A1 finish** — verify chests/barrels/shrines actually operate now that the AI
   is `MyPlayer` (the old companion guards should be moot); decide shrine policy.
2. **A2 tail** — wire the readied action / class skills (`RS=` is exposed): e.g.
   Warrior auto-Repair via skill, Rogue Disarm; offensive scroll use.
3. **B4 finish** — economic extraction (portal to sell when full) + the return
   trip; later, invite-the-human-through.
4. **A4 hazard awareness** — ✅ emit→parse→agent done (`HZ=` + `HazardAgent`).
   Remaining: live-test the dodge (Step 4) and v2 terrain hazards (lava tiles).
5. **D1 personality sliders** — weight biases over the council, with survival
   floors. Small once A4 lands; high character-per-line-of-code.
6. **D2 relationship adaptation** — feed observed player behavior (shares vs
   hoards) into the sliders via the memory system. Emergent personality.
7. **Track E decision tracing** — `--trace` JSONL of every `decide()` (recs +
   scores + commitment + winner + per-LLM prompt/response). Cheap, and it's the
   measurement substrate for B5 Phase 0 + the observability substrate for the
   lease — so it lands *first*. Unlocks offline weight/priority + behavior tests.
8. **B5 intent leases** — Phase 0 first (make the decorative vendor LLM calls
   rule-based/cached and *measure* via Track E — may dissolve the perceived
   sluggishness with no new primitive), then promote `CommitmentTracker` → a real
   lease with the ≥8-preempts / ≤7-leaseable tiers, a timeout backstop, and live
   lease observability. Foundational: loot/portal/vendor/follow simplify on top.
9. **B1 (light) / B3** — loot is mostly handled by the engine (first-click wins),
   so it's reduced to oscillation/efficiency and largely *falls out* of B5; B3
   stance arbitration shares the lease's preemption machinery — spec them with B5.
10. **B2** — formalize portal/level ownership & no-stranding (small TLA+ spec).
11. **Track C cleanup** — `gGapCompanionSlot` / `Source/seat/` dead code; debug
    markers; global `ENABLE_GAP`.

Rule of thumb: Track A is "go build it." Track B is "spec it small, then build it."
Don't pay for TLA+ on the framework while the framework is still moving — pay for
it on the protocol, one feature at a time, right when that feature lands.
