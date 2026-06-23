# GAP Roadmap — after true-MP + multiple AI clients

The framework is done. The AI is a true second player; multiple AI clients work
(Rogue + Sorc as players 2 & 3, 2026-06-23). Everything below was *postponed
until we had a working framework* — it's the backlog, not bugs.

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

### A2. Action system — default action, spells, skills, scrolls, mana
This is the biggest capability gap and deserves to be designed as one subsystem,
not bolted on piecemeal.
- **Model the readied-action mechanic.** The game has a selected "default action"
  (right-click) plus the full menu of anything you *know*, have *mana* for, or
  hold a *scroll/staff-charge* for. A Warrior starts with **Repair** as default.
- **Enumerate available actions** into the DSL: known spells, scroll inventory,
  staff charges (we already parse `st^charges:spellID`), default skill.
- **Selection policy:** which action for the situation (attack spell vs utility vs
  scroll). Today `spell.py` is stat-gated (Magic≥20) with a hardcoded priority —
  generalize it.
- **Mana awareness (likely missing entirely):** the DSL exposes `mp%` in `ME=`,
  but nothing budgets mana or **drinks a mana potion** when low (mirror the HP-
  potion logic in `healing.py`/belt refill). Confirm and add.

### A3. Inventory lifecycle (the "still-open" items fold in here)
- **Make room before grabbing:** sell/drop junk when the pack is full so a find
  isn't left on the floor. (Currently she just can't pick it up.)
- **Sell-loot loop:** the actual "offload old loot at Griswold" loop isn't
  implemented — needed for sustained dungeon runs.
- **Cain multi-item ID loop:** identify *all* unidentified items, prioritizing
  class-appropriate gear (not just the first).
- **Mark old gear for sale** after an upgrade swaps it out.

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

### B4. Adria / portal *production* (consumer → producer)
The step from *using* your portals to *making* its own:
```
need extraction → can I create a portal? → have the resource? → place it → coordinate party
```
Two providers behind one capability: **scroll-based** (buy a Town Portal scroll
from Adria — universal, any class) and **spell-based** (cast it — caster/mana).
Design it as a reusable **PortalCapability** an agent *possesses*, not a Rogue- or
Sorc-specific behavior — the same shape will serve any class. Depends on A2 (mana/
action system) and B2 (portal ownership).

---

## Track C — Cleanup (whenever)
- Remove inert sidecar dead code: `gGapCompanionSlot` across `multi.cpp`/`pfile.cpp`,
  and `Source/seat/` (already `!gGapHeadless`-gated, safe to delete carefully).
- Strip leftover debug `SDL_Log`/`std::cerr` markers; make `ENABLE_GAP` global.
- Push `GAP` (well ahead of origin) when ready.

---

## Suggested sequence
1. **A2 mana awareness** — small, high-value, confirms the gap (drink mana potions).
2. **A1 world interaction** — verify the MyPlayer-guard unlock; add operate command.
3. **A3 make-room + sell-loot** — unblocks sustained runs (and fixes the "left on
   floor" symptom at the source).
4. **A2 full action system** — spells/scrolls/default-action selection.
5. **B1 spec + build** — loot ownership, once multiple agents are actually looting
   the same floors hard enough to contend.
6. **B4 portal production** — the marquee coordination feature, after A2 + B2.

Rule of thumb: Track A is "go build it." Track B is "spec it small, then build it."
Don't pay for TLA+ on the framework while the framework is still moving — pay for
it on the protocol, one feature at a time, right when that feature lands.
