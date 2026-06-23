# GAP Milestone — June 22, 2026

**From a hacked-up sidecar proof-of-concept to a near-demo-worthy AI companion
that plays Diablo as a genuine second player.**

In one session the GAP companion went from a local "slot hack" wedged inside the
human's game client to its **own headless `devilutionx` client** that joins the
human's multiplayer game over TCP and plays as a real, independent player —
following through dungeons, taking battle orders, managing its own gear, and
chatting back. Along the way we deleted a large amount of the sidecar hackery
that made the old model fragile.

---

## The headline shift: sidecar → true multiplayer

**Before:** the AI was a *local companion slot* injected into the single human
client. The engine simulates exactly one level, so the companion was permanently
"leashed" to the human's level, and almost every action needed a `MyPlayer`-gated
special case. It was a clever hack, but a dead end.

**After:** the AI runs `./devilutionx --headless`, joins `127.0.0.1:6112` as a
real **player 2**, loads its own copy of the level, and drives its own
`MyPlayer`. Two real clients, syncing over the engine's normal `NetSendCmd`
pipe. The leash and the companion-slot injection are retired.

Key engine facts that made this work (and the traps we hit):
- Gate window/socket creation behind a `--headless` flag; **do not** use the
  unit-test `HeadlessMode` (it blanks all file loads, so the level never builds).
- `ENABLE_GAP` must reach **every** object library, not just the top target — it
  was silently compiled out of `multi.cpp` and others.
- `WorldTileCoord` is a `uint8_t`, so streaming it prints **char garbage**
  (`pos (0,O)`); every coordinate needs an `int` cast.

---

## What the companion can do now

### Plays alongside you, across levels
- **Stairs following** — when you descend, she walks to the *real* trigger tile
  (from `trigs[]`, direction-tagged down/up/warp so she takes the cathedral
  stairs, not the hell entrance) and the engine changes her level normally. She's
  `MyPlayer` in her own client, so standing on the trigger Just Works.
- **Town-portal following** — with caster-aware coordination: a portal closes when
  its *caster* crosses, so she rushes through **your** portal first, then **holds**
  on the far side for you instead of bouncing back ("go-first-then-hold").
- **Combat-aware transitions** — she won't abandon a survivable fight to follow;
  she only breaks off when she's genuinely doomed (low HP, no potions).

### Takes battle orders (the coordination capstone)
Speak terse, she adopts a stance and acks it:

| Say | Stance | Behavior |
|-----|--------|----------|
| "hold here" / "stay back" | **HOLD** | Holds position; still defends + heals |
| "go in" / "get him" | **ENGAGE** | Pushes the fight |
| "fall back" / "regroup" | **RETREAT** | Disengages to you, then resumes |
| "on me" / "with me" | **FOLLOW** | Default |

Intents are start-anchored so chatter ("I follow your logic") doesn't trip a
stance. This makes planning a boss pull actually meaningful.

### Manages its own gear (the upgrade loop)
Loot picks it up → Cain identifies it → **`EQUIP`** swaps it in, all network-correct:
- New **`EQUIP`** DSL command (`AutoEquip` + `CMD_CHANGEPLRITEMS`, with two-hand
  handling) — equipping like a real player, not a state poke.
- **ItemComparator** fixed: weapons compared as one primary slot (no more
  gear flip-flop), and class-biased so a Rogue keeps her bow instead of grabbing
  a higher-damage sword.
- Valuable class gear is mildly "magnetic" so she'll walk over for a real upgrade
  without snapping to every drop.

### Talks to you
- **Bidirectional chat over the network** — she hears you and replies with
  game-state awareness ("I don't currently have a bow equipped, but let's see if
  it's worth using").
- Replies are **word-chunked** under the 80-char wire limit (was truncating).

### Fights with what it's holding
- Combat style now follows the **equipped weapon**, not just the class — a Rogue
  with a sword closes to melee instead of kiting and whiffing.

---

## The cleanup that made it honest

Two fixes near the end mattered as much as any feature:

- **`A` — the GAP socket is now bound only by the headless client.** It used to be
  created on *every* client, so the human's own client also served the socket;
  the orchestrator could (and did, once) connect to the human's client and drive
  the human's character. Now: **one client, one player, no contention.**
- **`B` — retired the sidecar `GetControlledPlayer()` indirection.** Every GAP
  executor now drives `MyPlayer` directly; the slot-lookup wrappers, the
  `GapCore` controlled-slot machinery, and the Seat/CompanionSeat execution bridge
  are gone or gutted. (The remaining inert `gGapCompanionSlot` dead code across
  `multi.cpp`/`pfile.cpp` is flagged for a careful follow-up.)

---

## Bugs caught and fixed live

- **Item duplication** on pickup — the sidecar path did a local `AutoGetItem`
  *and* a manual broadcast; in true-MP both clients materialized the item. Now a
  single `CMD_REQUESTAGITEM` request that the host grants once.
- **Gear oscillation** — the upgrade agent flip-flopped weapons every tick because
  it treated each hand independently; fixed to a single primary weapon slot.
- **Griswold loop** — she'd wedge at the smith on a repair she couldn't afford;
  now defers and retries when she has gold.
- **Loot vs. follow priority** — a strong loot pick now pre-empts wandering/town
  chores so she grabs a find in front of her.

---

## Where it stands

The companion is a **clean, first-class second player**: its own client, its own
level, follows you by stairs and portals, fights and loots, equips upgrades,
takes tactical orders, and chats — with the sidecar tech-debt that made all of
this fragile largely deleted.

**Next up (not blocking a demo):**
- Finish the `gGapCompanionSlot` / `Source/seat/` dead-code removal.
- Strip remaining debug `SDL_Log` markers; make `ENABLE_GAP` global.
- Equip flow polish (Cain multi-ID, prefer her own dropped upgrades).

*Roughly 30 commits today — see `git log --since="2026-06-22"`. Architecture
overview lives in `CLAUDE.md` / `GAP-PROJECT-SUMMARY.md`.*
