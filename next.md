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

### A4. Hazard awareness — "see the fire" (⏳ prerequisite for combat smarts + Track D)
Today she can't perceive ground hazards at all: the DSL emits monsters/loot/
objects but **no danger layer** — Fire Wall, Inferno, Apocalypse rifts, Nova/
arcane blasts, lava/hazard terrain. So "MOVE OUT OF THE FIRE" is literally a
missing capability; she has the survival instincts of a houseplant because she's
standing in an *invisible* fire.
- **Emit a hazard layer in the DSL:** active hostile AoE/missile tiles + hazard
  terrain near her, as `HZ=x,y,kind;...` (kind = fire/lightning/arcane/…).
  Source from the missile list (like TP detection already does) + terrain flags.
- **Use it:** combat/movement avoid standing in/ pathing through hazard tiles;
  positioning prefers safe tiles. Helps every class regardless of personality.
- This is the gate for Track D's *fire tolerance* — you can't tune how much fire
  she'll stand in until she can see it.

---

## Track B — Coordination (write a small TLA+ spec just before each)

These are the party-protocol invariants. Each gets a scoped spec, then the build.

### B1. Item / loot ownership across agents  ← first candidate spec
With 2 AIs + you, who claims a drop? Invariants: **no duplicated ownership**, no
oscillation (A and B don't both walk to the same item forever), a claim resolves
or releases. We already hardened single-item pickup (the `_iRequest` debounce);
this is the *contention* layer on top.

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
4. **A4 hazard awareness** — emit a danger layer (`HZ=`) so she can see and avoid
   fire/AoE. Smarter combat now, and the prerequisite for Track D's fire tolerance.
5. **D1 personality sliders** — weight biases over the council, with survival
   floors. Small once A4 lands; high character-per-line-of-code.
6. **D2 relationship adaptation** — feed observed player behavior (shares vs
   hoards) into the sliders via the memory system. Emergent personality.
7. **B1 spec + build** — loot ownership, once multiple agents are contending for
   the same drops hard enough to matter.
8. **B2 / B3** — formalize portal/level ownership and stance arbitration (the
   place a small TLA+ spec earns its keep).
9. **Track C cleanup** — `gGapCompanionSlot` / `Source/seat/` dead code; debug
   markers; global `ENABLE_GAP`.

Rule of thumb: Track A is "go build it." Track B is "spec it small, then build it."
Don't pay for TLA+ on the framework while the framework is still moving — pay for
it on the protocol, one feature at a time, right when that feature lands.
