# DevilutionX GAP - Developer Guide

> **📚 For Architecture & Project Overview**: See [GAP-PROJECT-SUMMARY.md](./GAP-PROJECT-SUMMARY.md)
> **📋 This Document**: Implementation details, recent changes, development workflow

## Quick Reference

**Start Game + AI Companion** (two terminals; use the helper scripts):
```bash
# Terminal 1: launch the game (you = slot 0, AI = slot 1 from multi_1.sv).
# Then host a multiplayer game from the menu, password "foo".
cd /home/mental/Projects/DevilutionX/tools/gap
./launch_game.sh

# Terminal 2: launch the agent (waits for the game socket, then connects)
cd /home/mental/Projects/DevilutionX/tools/gap
./launch_agent.sh
```

`launch_agent.sh` runs `uv run orchestrator.py --model qwen2.5:3b --chat-model
gemma3:12b --password foo` under the hood. Override models/password via env, e.g.
`CHAT_MODEL=gemma3:27b ./launch_agent.sh`. Note: **the orchestrator has no
`--companion-slot` flag** — the slot is set on the *game* side only.

**Recommended Models** (dev box has a 32GB RTX 5090, so it's split-config by default):
- `qwen2.5:3b` - fast tactical/dungeon loop (the `--model`)
- `gemma3:12b` - chat/personality (the `--chat-model`); `gemma3:27b` for richer chat

**Build** (see Development Environment for why the pinned-deps flags are needed):
```bash
cmake -S . -B build -G Ninja -DENABLE_GAP=ON -DGAP_USE_DSL=1 \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DDEVILUTIONX_SYSTEM_LIBFMT=OFF -DDEVILUTIONX_SYSTEM_LUA=OFF
cmake --build build --target devilutionx
```

> Canonical agent entry point is **`orchestrator.py`** (multi-agent council).
> `dsl_agent.py` is the older single-loop agent, kept for reference only.

---

## Project Status (June 22, 2026)

> Revived on a fresh CachyOS box after sitting since Nov 2025. Build + full
> game↔agent loop confirmed working. See the June 2026 change-log entry below
> for the toolchain fixes, logic-bug fixes, commitment/hysteresis, and the
> personality-memory wiring added during the revival.

### ✅ Production-Ready Features

**Core Systems:**
- ✅ DSL protocol (100-200 bytes, 80-120 tokens)
- ✅ Multi-agent orchestrator with weighted voting
- ✅ SQLite persistent memory
- ✅ Character profile system (class-aware behavior)

**Combat:**
- ✅ Melee combat (direct attack functions)
- ✅ Ranged combat with kiting (no auto-pathing, true shift-key behavior)
- ✅ Spell casting (Magic ≥20, any class)
- ✅ Emergency survival reflexes (Python overrides)

**Town Services:**
- ✅ Pepin (healing purchase)
- ✅ Adria (spells, mana potions)
- ✅ Griswold (selling junk, **auto-repair damaged gear**)
- ✅ Cain (item identification)

**Equipment Management:**
- ✅ Item stat extraction (damage, AC, ToHit, durability)
- ✅ Durability tracking (current/max for equipped gear)
- ✅ Auto-repair detection (<75% durability → Griswold)
- ✅ Profile-aware loot (Rogues prioritize bows, Warriors prioritize swords)
- ✅ ItemComparator (weapon/armor scoring for upgrades)

**Social:**
- ✅ Bidirectional chat (reactive + proactive)
- ✅ Item requests ("give me a potion" → DROP command)
- ✅ First-person perspective ("I have" not "you have")

### 🚧 In Progress / Known Gaps

See [GAP-PROJECT-SUMMARY.md - TODO Section](./GAP-PROJECT-SUMMARY.md#todo-feature-gaps) for prioritized feature roadmap.

**High Priority Next Steps:**
- [ ] UpgradeAgent (use ItemComparator to find upgrades)
- [ ] EQUIP command (C++ - swap inventory to equipped slot)
- [ ] Multi-item Cain identification loop

---

## GAP-TRUE-MP: Headless Client Architecture (active work, this branch)

> Branch `GAP-TRUE-MP`. The goal: make the AI a **true second player**, not a
> local slot hack.

### Why
Today the companion is a local player slot in the single human client. The
engine loads/simulates exactly ONE level (the human's), so the companion can't
be on a different level — a "leash" (`diablo.cpp` `LoadGameLevelSyncPlayerEntry`)
teleports it onto the human's level on every transition. That blocks independent
behavior (e.g. portal to town to re-arm while the human keeps fighting) and forces
a pile of `MyPlayer`-gated workarounds.

### The plan
The AI runs its **own headless `devilutionx` client** that joins the human's
**TCP multiplayer game on localhost** as a real player 2. Each client runs its
own simulation with its own loaded level → the single-level constraint vanishes,
and the leash + companion-slot injection get **retired**. The headless client
owns the GAP DSL socket. State syncs over the engine's normal `NetSendCmd` pipe;
localhost keeps latency negligible as long as we never block the game loop.

### Engine facts (verified)
- `HeadlessMode` (Source/headless_mode.hpp) already exists but is set only in
  tests; it gates **rendering/assets**, NOT window/audio creation. Two ways to go
  headless: gate `init_create_window()`/`snd_init()` (`diablo.cpp:1283`,`:1340`)
  behind `!HeadlessMode`, OR run with `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`
  (no engine change — SDL fakes a window, asserts pass, render is a no-op).
- TCP provider exists (`Source/dvlnet/tcp_*`). Non-interactive join =
  `SNetInitializeProvider(SELCONN_TCP, gameData)` + `SNetJoinGame("127.0.0.1:6112",
  password, &playerId)`, replacing the `UiSelectProvider`/`UiSelectGame` block in
  `InitMulti` (`multi.cpp:510-520`). Set `gbSelectProvider=false`,
  `gbIsMultiplayer=true`.
- Hero loads via `gSaveNumber = ParseSaveNumber("multi_1.sv")` before `NetInit`,
  consumed at `multi.cpp:530` (`pfile_read_player_from_save`). `MyPlayerId` is
  assigned by the host handshake (`base.cpp` `HandleAccept`) — do NOT hard-code.
- Menus to bypass (mirror demo mode's non-interactive start, `menu.cpp:164`/`111`):
  `UiMainMenuDialog`, `UiSelHeroMultDialog`, `UiSelectProvider`, `UiSelectGame`.
  `SNetInitializeProvider` already auto-skips the hero dialog in headless
  (`storm_net.cpp:131`).
- GAP pump is ALREADY in the authoritative tick (`diablo.cpp:3577 ProcessIntents`,
  `:3584 OnGameTick`) and packets at `:985` — a real joining client reaches them
  for free.

### The catch (do not forget)
True 2-client MP is **lockstep-deterministic**. The current GAP code drives the
companion with DIRECT calls (`StartAttack`, `AutoGetItem`, direct state pokes)
that work with one client but will **desync** two. AI actions must route through
the network command layer (`NetSendCmd*`) — i.e. actually honor the "companions
as first-class players, no special cases" principle. The leash era let us cheat;
this era makes us honest.

### Increments
1. **Headless boot stable** — `--headless` flag sets `HeadlessMode=true`; boot via
   dummy SDL drivers; verify a clean startup (no window, no crash).
2. **Non-interactive TCP join** — bypass menus, wire `SNetInitializeProvider` +
   `SNetJoinGame`, load `multi_1` via `gSaveNumber`; confirm it joins a hosted
   localhost game and runs the loop headless.
3. **Network-correct GAP execution** — move command executors from direct calls
   to `NetSendCmd*` so two clients stay in sync.
4. **Retire** the leash + companion-slot injection; build stairs/portals the
   normal way (the AI is just `MyPlayer` in its own client).

Merge to `GAP` only when unbroken.

## Recent Changes Log

### June 22, 2026: Revival + Agency/Memory Pass ✅

Dusted off on a fresh CachyOS box (GCC 16 / fmt 12 / Lua 5.5) and pushed the
companion toward being a first-class peer.

**Build revival (toolchain was newer than the pinned deps):**
- `BUILD_TESTING=OFF` (skips google-benchmark), `DEVILUTIONX_SYSTEM_LIBFMT=OFF`
  (system fmt 12 dropped `fmt::format` from `<fmt/core.h>`), `DEVILUTIONX_SYSTEM_LUA=OFF`
  (system Lua 5.5 breaks sol2). Added explicit `#include <cstdint>` to all
  `Source/gap/*.cpp` (GCC 16 dropped the transitive include).
- Documented `--companion-save`/`--companion-slot` in `--help`.

**Tooling:**
- `tools/gap/launch_game.sh` and `launch_agent.sh` helpers.
- Python deps now tracked in `pyproject.toml` via **uv** (`uv sync`, `uv run`);
  only real runtime dep is `requests`. `requirements.txt` removed.

**Agent logic fixes (found while play-testing):**
- ShoppingAgent: force the real store index (model was copying the prompt's
  example `BUY hl 1`, buying the wrong/unaffordable item → infinite loop).
- LootAgent: only count a pickup as failed after a real adjacent `PK`, not
  while walking toward an item — premature blacklisting fixed.
- Chat: 60s timeout + `keep_alive=30m` so the 12B chat model doesn't time out
  or get evicted between messages.

**Council commitment/hysteresis (`CommitmentTracker` in orchestrator.py):**
- Boosts the committed goal and damps fallback agents during a transient gap,
  so she finishes a goal instead of pacing. Avg goal-run went ~1-3 → ~9 ticks.
- Graceful disconnect: agent detects a closed socket (EOF) and shuts down with
  a session reflection instead of spinning on a dead socket.

**Personality wired into behavior (roadmap item #2):**
- `PersonalityStore.get_behavioral_context()` synthesizes a first-person
  preamble (traits + emotional memories + proven strategy), injected into chat
  and strategic-agent prompts (tactical agents opt out via `use_memory_context`).
- Learning loop: combat win/loss records a per-floor strategy; `decide()` nudges
  Combat's weight x1.1 where the approach has worked, x0.7 where it's been
  getting her killed.

**Next milestone:** autonomous level transitions (stairs + town portals to
re-arm/sell/repair and rejoin) — the companion still can't change levels on its
own; the engine is hacked to keep her with the player. See GAP-PROJECT-SUMMARY.

### November 4, 2025: Personality Persistence System ✅

**Phase 1 Complete - Core Infrastructure:**

Implemented SQLite-backed personality system enabling companion AI to remember experiences and grow across sessions.

**Bootstrap Pattern**: Same concept as CLAUDE.md bootstrapping AI assistant state → personality DB bootstraps companion state.

**Implementation Details:**
- **Schema** (`tools/gap/schema/personality.sql`):
  - `personality_traits` - Evolving traits (risk_tolerance, player_relationship) with confidence levels
  - `memories` - Episodic events (deaths, victories, gifts) with emotional impact (-1.0 to 1.0)
  - `learned_strategies` - Success/failure tracking with confidence scores
  - `prompt_injections` - Dynamic context injection into agent prompts
  - `session_reflections` - LLM-generated end-of-session summaries

- **PersonalityStore Class** (`tools/gap/personality_store.py`, ~312 lines):
  - `load_personality()` - Load traits/memories/strategies on startup
  - `update_trait()` - Modify personality traits with context
  - `add_memory()` - Record significant events with emotional impact
  - `add_strategy()` - Track what works/doesn't work, calculate confidence
  - `get_prompt_context()` - Generate personality context for agent prompts
  - `save_session_reflection()` - End-of-session LLM summary

- **Orchestrator Integration** (`tools/gap/orchestrator.py`):
  - Personality initialization on startup
  - Session stats tracking (battles, deaths, victories, near_deaths, gifts, levels_cleared)
  - SIGINT/SIGTERM signal handlers for graceful shutdown
  - `_shutdown_handler()` - Save state and generate reflection on Ctrl+C
  - `_save_session_reflection()` - LLM reflects on gameplay session before exit

**Example Usage Flow:**
```python
# On startup
personality.load_personality()  # Load traits, memories, strategies

# During gameplay
personality.add_memory("death", "Killed by Butcher", -0.8, "level_2", "Butcher")
personality.add_strategy("facing_butcher", "retreat_to_stairs", success=True)
personality.update_trait("risk_tolerance", "cautious", 0.8, "Nearly died to Butcher")

# On Ctrl+C
# LLM generates: "Learned to retreat from tough enemies. Player is supportive."
personality.save_session_reflection(reflection, stats)
```

**Testing:**
- ✅ All tests pass (`test_personality.py`)
- ✅ Database creation and schema verified
- ✅ Persistence across restarts confirmed
- ✅ Graceful shutdown with reflection works

**Next Steps (Phase 2):**
- Integrate personality updates into combat/chat/healing agents
- Add prompt injection to BaseAgent (inject personality context into agent decisions)
- Test personality continuity across multiple gameplay sessions

**Files Created/Modified:**
- `tools/gap/schema/personality.sql` - Database schema (64 lines)
- `tools/gap/personality_store.py` - PersonalityStore class (312 lines)
- `tools/gap/test_personality.py` - Test suite (178 lines)
- `tools/gap/orchestrator.py` - Signal handlers + session stats (modified lines 13-14, 32, 67-82, 129-221)

---

### November 4, 2025: Equipment Stats & Auto-Repair

**Item Stat Tracking:**
- Extended DSL format to include equipment stats (damage, AC, ToHit, durability)
- Format: `sw_m:3-6+2:15:45/60` (magic sword: 3-6 dmg, +2% bonus, +15 ToHit, 45/60 durability)
- Format: `la_m:25+5:40/50` (magic light armor: 25 AC, +5 Str, 40/50 durability)
- Updated `dsl_parser.py` to parse weapon and armor stats with durability

**ItemComparator Class** (`tools/gap/item_comparator.py`):
- Weapon scoring: avg_damage * (1 + to_hit/100) * class_bonus
- Armor scoring: AC + (stat_bonus * 2.0) * class_bonus
- Smart thresholds: 10% improvement for weapons, 8% for armor
- Quality bonuses: unique/magic items get extra value
- `find_upgrades()` - scans inventory for all potential equipment upgrades

**Griswold Auto-Repair:**
- Detects damaged equipment (<75% durability)
- Prioritizes repairs BEFORE selling (lines 96-119 in griswold.py)
- Urgency levels: <30% = URGENT (weight 0.75), <75% = RECOMMENDED (weight 0.6)
- Command: `REPAIR <body_slot_index>` (0=head, 4=hand_left, 5=hand_right, 6=chest)

**LootAgent Profile Integration:**
- 30% score boost for preferred weapon types
- 20% score boost for preferred armor types
- 50% extra boost for unidentified magic/unique items of class-appropriate types
- Rogue sees unidentified magic bow → HIGH PRIORITY pickup for Cain

**Files Modified:**
- `Source/gap/gap_dsl.cpp` - Added durability to equipment stats (lines 377-428)
- `tools/gap/dsl_parser.py` - Parse durability values (lines 314-369)
- `tools/gap/item_comparator.py` - NEW FILE (360 lines)
- `tools/gap/agents/griswold.py` - Repair detection + prioritization (lines 28-280)
- `tools/gap/agents/loot.py` - Profile-aware scoring (lines 175-190)

**Agent Perspective Verification:**
- ✅ Confirmed: All chat prompts use first-person ("I'm wielding", "I have")
- ✅ CharacterProfile: "You are a level 3 Rogue" (correct perspective for AI)

### November 3, 2025: Spell Casting System

**C++ Implementation:**
- Exported `StartSpell()` from player.cpp (lines 1483-1525)
- Added `CAST spell_id x y` DSL command parsing
- `ExecuteCastSpell()` - validates spell memorized, checks mana, calls StartSpell() directly (no auto-pathing)
- Uses direct function call pattern (same as ranged combat)

**Python SpellAgent** (`tools/gap/agents/spell.py`):
- Priority 9 (just below healing at 10)
- Activates when Magic ≥20 (any class can cast if they have the stat)
- Spell selection: Fireball (AoE), Lightning (fast), Firebolt (cheap)
- Cooldown: 20 ticks between casts
- Profile-aware logging: "Warrior Spell: Firebolt" vs "Spell: Lightning"

**Files Modified:**
- `Source/player.cpp/h` - Export StartSpell
- `Source/gap/gap_intent.cpp/h` - CAST command + ExecuteCastSpell
- `tools/gap/agents/spell.py` - NEW FILE (214 lines)
- `tools/gap/orchestrator.py` - SpellAgent integration (priority 9)

### November 3, 2025: Ranged Combat Fix

**Problem**: Rogue with bow was running into melee range (face-tanking)

**Root Cause**: `destAction = ACTION_ATTACKMON` triggers game engine auto-pathing, which creates movement paths even after `ClrPlrPath()`.

**Solution**: Direct function calls instead of queuing actions

```cpp
// ✅ NEW WAY - True shift-key behavior
if (player.UsesRangedWeapon()) {
    StartRangeAttack(player, dir, monsterPos.x, monsterPos.y, true);
} else {
    StartAttack(player, dir, true);
}
// Result: Attack animation starts from current position, NO movement
```

**Files Changed:**
- `Source/player.h` - Export StartAttack/StartRangeAttack (lines 968-969)
- `Source/player.cpp` - Move functions out of anonymous namespace (lines 169-232)
- `Source/gap/gap_network.cpp` - Direct function calls + range checks (lines 172-212)
- `tools/gap/agents/combat.py` - Ranged positioning logic (lines 181-246)

**Key Lesson**: For AI tactical control, call underlying action functions directly to bypass auto-pathing. Apply this pattern to spells, abilities, any position-critical action.

### November 3, 2025: Mutual Support System

**DROP Command** (C++):
- `DROP <inv_slot>` - Drop item from inventory
- `DROP GOLD <amount>` - Drop gold pile
- Uses `FindAdjacentPositionForItem()` and `CMD_PUTITEM`

**Chat Item Detection** (Python):
- Natural language: "give me a potion" → searches inventory → generates DROP command
- Response: "Sure! Dropping a healing potion for you now."

**Anti-Pickup Loop**:
- LootAgent tracks `recently_dropped` positions
- Items ignored for 10 seconds (200 ticks) at drop location
- Prevents companion from immediately picking back up

**Files Modified:**
- `Source/gap/gap_intent.h/cpp` - DROP command
- `tools/gap/agents/chat.py` - Item request detection
- `tools/gap/agents/loot.py` - Recently dropped blacklist
- `tools/gap/orchestrator.py` - DROP tracking

---

## Critical Design Principles

### 1. Companions as First-Class Players

**Rule**: AI companions must be indistinguishable from real multiplayer players to the game engine. Never create special case logic.

**Examples:**

✅ **Universal Damage System:**
```cpp
// ✅ GOOD: Works for any player
ApplyPlrDamage(DamageType::Physical, player, 0, 0, dam);

// ❌ BAD: Special cases
if (player.getId() == MyPlayerId) {
    ApplyPlrDamage(...);  // Only human
}
```

✅ **Missile Damage** (Nov 3, 2025):
- Fixed companions being invulnerable to fireballs/arrows/acid/lightning
- Removed `if (&player == MyPlayer)` restriction in `missiles.cpp` (lines 332-334, 1138-1150)
- Now companions take damage from ANY missile source, just like real players

**Code Review Questions:**
- Does this code treat companions differently than multiplayer players?
- Would this work if player 2 joined a multiplayer game?
- Are we adding complexity instead of removing restrictions?

### 2. Direct Function Calls for Tactical Control

**Problem**: `destAction` queuing triggers auto-pathing (good for humans, bad for AI)

**Solution**: Call underlying action functions directly with last parameter `true` (shift-key behavior)

**Pattern:**
```cpp
// Ranged attack (no pathfinding)
StartRangeAttack(player, dir, targetX, targetY, true);

// Melee attack (no pathfinding)
StartAttack(player, dir, true);

// Spell casting (no pathfinding)
StartSpell(player, dir, targetX, targetY, spell_id, true);
```

**When to use**: Any action requiring tactical positioning (ranged, spells, abilities)

### 3. Hybrid Architecture (LLM + Python + C++)

**LLM**: Strategic decisions (target selection, chat, shopping preferences)
**Python**: Tactical execution (kiting math, emergency healing, stat comparison)
**C++**: Pure execution (pathfinding, combat calculations, rendering)

See [GAP-PROJECT-SUMMARY.md - What's LLM vs What's Code](./GAP-PROJECT-SUMMARY.md#whats-llm-vs-whats-code) for detailed breakdown.

---

## Development Workflow

### Adding a New Agent

1. **Create agent file** in `tools/gap/agents/`
2. **Inherit from BaseAgent** (`tools/gap/agents/base.py`)
3. **Implement methods**:
   - `should_activate(state)` - When should this agent run?
   - `_evaluate_impl(state)` - Return `AgentResponse` with command + weight
4. **Add to orchestrator** (`tools/gap/orchestrator.py`):
   - Import agent
   - Initialize in `__init__`
   - Add to agent list with priority
5. **Test in isolation** before integrating

**Example Skeleton:**
```python
from .base import BaseAgent, AgentResponse

class MyNewAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="MyNew", **kwargs)

    def should_activate(self, state):
        # When should this agent run?
        return state.get("some_condition")

    def _evaluate_impl(self, state):
        # What action should we take?
        return AgentResponse(
            command="MV 50 50",
            weight=0.6,
            reasoning="MyNew: Going somewhere"
        )
```

### Adding a New DSL Command

**C++ Side:**
1. **Parse command** in `Source/gap/gap_intent.cpp` (add to `ParseIntent()`)
2. **Implement executor** (e.g., `ExecuteMyCommand()`)
3. **Add to command list** in `ProcessIntent()`

**Python Side:**
1. **Generate command** from agent logic
2. **Test with logs** to verify parsing/execution

**Example Flow:**
```
Python: "MYCMD 42 100"
   ↓
C++: ParseIntent() → creates Intent with type=MYCMD, params={42, 100}
   ↓
C++: ExecuteMyCommand() → performs game action
   ↓
Logs: "GAP: ExecuteMyCommand - param1=42, param2=100"
```

### Debugging Tips

**Follow the flow:**
1. **Python logs** - Agent decision + command generation
2. **DSL command** - What was sent over socket?
3. **C++ logs** - Was it parsed correctly?
4. **Game behavior** - Did it execute as expected?

**Common Issues:**
- **Command not executing**: Check if it's in `ProcessIntent()` switch
- **Wrong player executing**: Verify `GetControlledPlayer()` returns companion slot
- **Auto-pathing interfering**: Use direct function calls instead of `destAction`
- **LLM hallucination**: Add grammar constraint (GBNF) to force valid syntax

---

## DSL Protocol Reference

### State Format (Compact, 100-200 bytes)

```
T=12345 F=2 ME=34,18,72,33 PLYR=51,54 M=12@38,16,55,1;19@36,17,20,1 L=71@35,19,10
```

**Fields:**
- `T=tick` - Game tick (timestamp)
- `F=floor` - Floor/level (0=town, 1-16=dungeon)
- `ME=x,y,hp%,mp%` - Companion position and vitals
- `PLYR=x,y` - Main player position (for following)
- `M=id@x,y,hp%,flags;...` - Monsters (flags: bit 0=hostile, 1=unique, 2=ranged)
- `L=id@x,y,value;...` - Loot items
- `EQ=slot:type;...` - Equipped gear with stats
- `INV=type@slot;...` - Inventory items with stats
- `NPC=type@x,y,id;...` - Town NPCs
- `GOLD=amount` - Current gold

**Equipment Stats Format:**
- **Weapon**: `sw_m:3-6+2:15:45/60` (type:minDam-maxDam+bonus:toHit:dur/maxDur)
- **Armor**: `la_m:25+5:40/50` (type:AC+statBonus:dur/maxDur)

### Command Format (Output by agents)

```
MV x y              # Move to coordinates
AT x y              # Attack position (ranged, no pathfinding)
AT id               # Attack monster ID (melee, paths to target)
PK id               # Pick up item
CAST spell_id x y   # Cast spell at position
REPAIR slot         # Repair equipped item (0-6)
DROP slot           # Drop inventory item
DROP GOLD amount    # Drop gold
IN npc_id           # Interact with NPC
SAY message         # Chat with player
SELL slot           # Sell inventory item
BUY store item_idx  # Buy from store
ID slot             # Identify item at Cain
```

---

## Technical Debt & Known Issues

### High Priority

**Equipment Upgrade Workflow:**
- [ ] Create UpgradeAgent to use ItemComparator.find_upgrades()
- [ ] Implement EQUIP command (C++ side - swap inventory → equipped)
- [ ] Mark old equipment for selling after upgrade

**Cain Multi-Identification:**
- [ ] Loop through all unidentified items, not just first one
- [ ] Prioritize class-appropriate items (bows for Rogue, swords for Warrior)

### Medium Priority

**Dungeon Objects:**
- [ ] Add chest/barrel/shrine detection to DSL state
- [ ] Create exploration agent for object interaction
- [ ] Safety checks (don't open chest with 5 monsters nearby)

**Economic Intelligence:**
- [ ] Track gold budget (essential vs luxury purchases)
- [ ] Value assessment (save gold for better gear vs buy potions now)

### Known Restrictions (Pending Decisions)

**Shrines** (30+ types):
- Current: All shrines check `if (&player != MyPlayer) return;`
- Impact: Companions cannot activate shrines at all
- Question: Should companions use shrines autonomously? Many have downsides (stat swaps, curses)

**Fountains** (3 types):
- Current: Blood/Purifying/Tear fountains restrict to `MyPlayer`
- Impact: Companions cannot drink from fountains
- Question: Intentional resource limit or should companions access?

**Barrels**:
- Current: `if (!forcebreak && &player != MyPlayer) return;`
- Impact: Companions won't break barrels during exploration
- Question: Should companions autonomously break barrels for loot/spawns?

See `Source/objects.cpp` for details.

---

## Development Environment

### Setup (First Time)

```bash
# 1. Build game with GAP enabled (top-level ./build; pinned-deps flags are
#    required on bleeding-edge toolchains — see "Build prerequisites" below)
cd /home/mental/Projects/DevilutionX
cmake -S . -B build -G Ninja -DENABLE_GAP=ON -DGAP_USE_DSL=1 \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DDEVILUTIONX_SYSTEM_LIBFMT=OFF -DDEVILUTIONX_SYSTEM_LUA=OFF
cmake --build build --target devilutionx

# 2. Setup Python environment (uv)
cd tools/gap
uv sync                 # creates .venv from pyproject.toml (only dep: requests)

# 3. Install Ollama and models
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b
ollama pull gemma3:12b   # (gemma3:27b optional, for richer chat)

# 4. Game data: drop retail DIABDAT.MPQ where the game can find it (build/ or
#    ~/.local/share/diasurgical/devilution/). GoG installer -> innoextract.
```

#### Build prerequisites (why the extra flags)

The dev box ships a toolchain newer than the pinned deps, so a bare
`cmake -DENABLE_GAP=ON` fails. The flags force the project's bundled fmt (11)
and Lua (5.4) and skip the test-only google-benchmark. The active game data dir
is `~/.local/share/diasurgical/devilution/` (saves + `diablo.ini` live there;
`multi_0.sv` = you, `multi_1.sv` = the AI companion).

### Daily Development

```bash
# Quick rebuild after C++ changes
cd /home/mental/Projects/DevilutionX
cmake --build build --target devilutionx

# Run game + agent (two terminals)
cd tools/gap
./launch_game.sh         # then host a multiplayer game, password foo
./launch_agent.sh        # in a second terminal
```

### Development Scripts

```bash
cd tools/gap

./dev.sh run      # Launch the AI companion agent (= launch_agent.sh)
./dev.sh test     # Personality tests + DSL parser self-test
./dev.sh format   # Format code with black (via uv)
./dev.sh lint     # Check code with ruff (via uv)
./dev.sh fix      # Auto-fix lint issues
./dev.sh clean    # Clean logs and cache
```

---

## Python Notes

- **Line endings**: Always use `\n` (Unix), never `\r\n` (Windows)
- **Platform**: Developed on Linux, uses Unix domain sockets
- **Python version**: 3.8+ (pyproject `requires-python`); dev box runs 3.14
- **Deps/run**: managed by **uv** (`uv sync`, `uv run`); only runtime dep is `requests`

---

## Chat Commands (In-Game)

```
!ai help      # Show available commands
!ai status    # Display companion state
!ai debug     # Show debug information
```

---

## File Structure

```
Source/gap/              # C++ GAP integration
├── gap_dsl.cpp          # DSL state encoder
├── gap_intent.cpp       # DSL command parser
├── gap_network.cpp      # Socket IPC + command execution
└── gap_stores.cpp       # Store interaction helpers

tools/gap/               # Python agent system
├── launch_game.sh       # Launch game with companion args (you=0, AI=1)
├── launch_agent.sh      # Launch the orchestrator (waits for socket)
├── orchestrator.py      # Multi-agent coordinator + CommitmentTracker
├── dsl_parser.py        # DSL state parser
├── memory_store.py      # SQLite persistent memory (spatial/goals)
├── personality_store.py # Per-character traits/memories/strategies + reflection
├── character_profile.py # Class-aware behavior
├── item_comparator.py   # Equipment upgrade detection
├── dsl_agent.py         # Legacy single-loop agent (reference only)
└── agents/              # Specialized agents (base.py = BaseAgent)
    ├── combat.py        # Combat decisions      ├── chat.py     # Conversation
    ├── healing.py       # Potion usage          ├── spell.py    # Spell casting
    ├── loot.py          # Item pickup           ├── shopping.py # Buy potions/gear
    ├── town.py          # NPC navigation        ├── griswold.py # Selling, repair
    ├── cain.py          # Item identification   ├── adria.py    # Witch shop
    ├── inventory.py     # Belt refills          ├── stats.py    # Stat allocation
    ├── movement.py      # Follow/explore        └── exploration.py # Chests/doors
```

---

*Last Updated: November 4, 2025*
*For architecture overview, see [GAP-PROJECT-SUMMARY.md](./GAP-PROJECT-SUMMARY.md)*
