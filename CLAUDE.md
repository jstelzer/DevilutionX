# DevilutionX GAP Project

GAP (Game Agent Protocol) enables LLM control of Diablo characters via IPC/JSON protocol.

> **📋 Single Source of Truth**: This document contains the complete GAP roadmap and implementation guide. The `docs/gap-evolution-roadmap.md` content has been integrated here for unified reference.

## Project Overview
- **Goal**: Run an LLM on NVIDIA GPU to play Diablo autonomously/cooperatively
- **Architecture**: Unix socket IPC, JSON protocol, compile flag `-DENABLE_GAP`
- **Integration**: Hooks in `game_loop()` for state, `GameEventHandler()` for input
- **Status**: Multiplayer companion mode with chat fully functional
## Documentation

- **docs**: Review the ./docs directory for context.

## Notes

* When generating scripts/python note I'm on linux so only use \n not \r\n for line ending.s

## Completed Features Summary

**Phase 1-3.5 Complete**: Basic protocol, combat, LLM integration, level transitions all working.

### Key Achievements:
- ✅ **GAP Protocol**: Unix socket IPC with JSON messaging
- ✅ **State Extraction**: Player, monsters, items, vision system  
- ✅ **Combat System**: Attack, movement, tactical behaviors
- ✅ **LLM Integration**: Ollama bridge via MCP server
- ✅ **Level Transitions**: Automatic companion following through stairs/portals
- ✅ **Chat System**: Bidirectional conversation with AI companion
- ✅ **Multiplayer Mode**: Companion loads from save files

### Current Usage:
```bash
# Start game with companion
./devilutionx --companion-save multi_1.sv --companion-slot 1

# Start AI agent
python3 tools/gap/mcp_server.py --companion-slot 1 --model qwen2.5:3b --password "foo"
```

**Recommended Models**: qwen2.5:3b (fast), llama3.2:latest (balanced), llama3.1:8b (powerful)

## Active Development Focus

### ✅ DSL Migration Complete! (November 2025)

**Problem**: JSON protocol was slow (500ms-2s decisions), token-heavy (400-600 tokens/call), and stateless

**Solution**: Migrated to compact DSL + SQLite memory system

**Results Achieved**:
- ✅ 10x smaller messages (1-2KB → 100-200 bytes)
- ✅ 5x fewer tokens (400-600 → 80-120)
- ✅ 2-4x faster decisions (500ms-2s → 200-500ms)
- ✅ Persistent SQLite memory (spatial awareness, goal tracking)
- ✅ Grammar constraints force valid DSL output
- ✅ Risk signals (RISK=high/med/low, SAFE_TILE, BEST_LOOT)
- ✅ Async chat handler (template-based, non-blocking)
- ✅ Python survival/combat overrides (HP<30% retreat, HP>35% attack)

**Agent Stack** (`tools/gap/`): `dsl_agent.py`, `dsl_parser.py`, `chat_handler.py`, `memory_store.py`

### ✅ Ranged Combat System Complete! (Nov 3, 2025)

**Problem**: Rogue companion with bow was face-tanking enemies instead of using ranged tactics

**Root Cause**: Using `destAction = ACTION_ATTACKMON` triggered the game engine's auto-pathing system, which created movement paths to targets even after calling `ClrPlrPath()`. The engine recreates paths during attack processing.

**The Critical Solution - Direct Function Calls**:

Instead of queuing actions via `destAction` (which triggers engine auto-pathing), we **call attack functions directly**:

```cpp
// ❌ OLD WAY - Triggers auto-pathing
player.destAction = ACTION_ATTACKMON;
player.destParam1 = monster_id;
// Result: Engine creates path to target, companion runs to monster

// ✅ NEW WAY - True shift-key behavior
if (player.UsesRangedWeapon()) {
    StartRangeAttack(player, dir, monsterPos.x, monsterPos.y, true);
} else {
    StartAttack(player, dir, true);
}
// Result: Attack animation starts from current position, NO movement
```

**Implementation Steps**:
1. **Export functions from player.cpp** (Source/player.h:968-969):
   - Moved `StartAttack()` and `StartRangeAttack()` OUT of anonymous namespace
   - Added public declarations: `void StartAttack(Player&, Direction, bool)` and `void StartRangeAttack(Player&, Direction, WorldTileCoord, WorldTileCoord, bool)`

2. **Call directly from GAP** (Source/gap/gap_network.cpp:202-212):
   - Replaced `destAction = ACTION_ATTACKMON` with direct function calls
   - Added range validation: bow ≤15 tiles, melee ≤1 tile
   - Functions start attack animations **without creating movement paths**

3. **Python agent tactics** (tools/gap/agents/combat.py:181-246):
   - **4-10 tiles**: `AT x y` - Attack from current position (optimal bow range)
   - **<4 tiles**: `MV away` - Kite backwards to safety
   - **>10 tiles**: `MV toward` - Move to 8-tile optimal range first

**Files Changed**:
- `Source/player.h` - Export StartAttack/StartRangeAttack declarations
- `Source/player.cpp` - Move functions out of anonymous namespace (lines 169-232)
- `Source/gap/gap_network.cpp` - Direct function calls + range checks (lines 172-212)
- `tools/gap/agents/combat.py` - Ranged positioning logic

**Status**: ✅ **WORKING** - Companion now stands and shoots, maintains distance, kites when needed

**Apply This Pattern To**:
- ✅ Ranged attacks (done)
- 🔮 **Spell casting** (next) - Same issue will occur, use `StartSpell()` directly
- 🎯 **Targeted abilities** - Any action that needs position control

**Key Lesson**: `destAction` is for human input processing where auto-pathing is desired. For AI companions that need tactical positioning control, call the underlying action functions directly to get true "shift-key" behavior.

### ✅ Town Agent Fixes (Nov 3, 2025)

**Problem 1: NPC Interaction Loops**
- Agents tried to move to NPC's exact tile position (e.g., Griswold at 62,63)
- NPCs block their own tiles, causing infinite movement loops
- Companion gets close (dist=2-3) but can't reach exact position

**Solution**: Increase interaction range from `dist <= 1` to `dist <= 3` and use `IN {npc_id}` command instead of trying to move to blocked tile.

**Files Fixed**:
- `tools/gap/agents/town.py` - Pepin and Adria interaction distances (lines 60-106, 119-140)
- `tools/gap/agents/griswold.py` - Griswold interaction distance (lines 119-153)

**Problem 2: Griswold Selling Logic Unreachable**
- Agent had early returns for `dist <= 3` (interact) and `dist > 3` (navigate)
- Selling logic (lines 155-195) was **completely unreachable** - never executed
- Agent opened shop then walked away, infinite loop

**Root Cause**: Logic structure:
```python
if dist <= 3:
    return interact_command  # Early return!
if dist > 3:
    return move_command      # Early return!
# Lines below NEVER execute
sell_logic_here()
```

**Solution**: Check shop status FIRST, only return early if shop NOT open:
```python
shop_is_open = "sm" in stores and len(stores.get("sm", [])) > 0

if shop_is_open:
    # Fall through to selling logic below (no early return)
    pass
elif dist <= 3:
    return interact_command  # Open shop
else:  # dist > 3
    return move_command      # Navigate closer

# Selling logic now reachable!
sell_item_with_llm()
```

**Problem 3: Inventory Fullness Check Too Strict**
- Shop opens, enters selling logic
- Checks inventory: 16/40 = 40% full
- Logic: `if inv_fullness <= 0.4: return None`
- Returns None even though shop already open and has sellable items!

**Solution**: If shop is already open, sell items regardless of inventory fullness. Fullness affects WEIGHT (urgency) but not whether to sell:
```python
else:
    # Shop is already open, might as well sell even if inventory not full
    weight = 0.25  # Low priority
    urgency = "OPTIONAL"
```

**Files Changed**:
- `tools/gap/agents/griswold.py` (lines 119-172)

**Result**: Companion now properly navigates to NPCs, opens shops, and sells junk items without getting stuck in loops.

**Key Lessons for Future Inventory/Shopping Work**:
1. NPCs block their tiles - use interaction range ≥3, not exact positioning
2. Check "already open" state BEFORE early returns, or logic becomes unreachable
3. Separate "should activate" logic (inventory fullness for opening shop) from "execute" logic (sell once shop open)

## Next Features to Implement

### 🔮 Spell Casting (High Priority)
**Apply direct function call pattern** - Same issue as ranged attacks will occur with `destAction = ACTION_SPELL`. Need to:
1. Find spell casting function in player.cpp (likely `StartSpell()` or similar)
2. Export it from anonymous namespace to player.h
3. Call directly from `gap_network.cpp` for position-controlled casting
4. Add to DSL: `CAST spell_id target_x target_y` command

**Expected Behavior**: Casters should cast from safe distance without auto-pathing into melee range

### 📦 Lootable Objects in Dungeons (High Priority)
**Problem**: Currently only tracks ground loot (items dropped by monsters). Missing dungeon interactables:
- Chests (wooden, trapped, locked)
- Barrels (can contain items/gold)
- Tombs/Sarcophagi (skeleton spawn + loot)
- Shrines (buff effects)
- Bookstands (lore/spells)

**Implementation Needed**:
1. **State Extraction** (`Source/gap/gap_state.cpp`):
   - Add object detection similar to monster/item extraction
   - Extract: object type, position, interactable state
   - DSL format: `OBJ=type@x,y;...` (e.g., `OBJ=chest@45,23;barrel@46,25`)

2. **Python Agent** (`tools/gap/agents/`):
   - Create `exploration.py` or extend existing agents
   - Priority: Chests > Barrels > Tombs
   - Pathfinding: Navigate to object, send `IN {object_id}` to interact
   - Safety: Check for nearby monsters before opening (avoid ambushes)

3. **DSL Commands**: Reuse `IN {object_id}` command (same as NPC interaction)

**Why Important**:
- Major loot source (chests often have best items)
- Exploration completeness (companions should open everything)
- Tactical decisions (skip barrels in combat, open chests when safe)

**Reference**: Object interaction uses same pattern as NPC interaction - use range ≥3, send `IN` command

### 💰 Other Planned Features
1. Gold tracking and economic decisions
2. Equipment comparison and upgrades
3. Multi-enemy threat prioritization
4. Spell/ability cooldown management

## GAP Protocol Data Structure (DSL Format)

### Current DSL State Format (100-200 bytes):
```
T=12345 F=2 ME=34,18,72,33 PLYR=51,54 M=12@38,16,55,1;19@36,17,20,1 L=71@35,19,10;83@37,18,250
```

**Format Breakdown**:
- `T=12345` - Game tick (timestamp)
- `F=2` - Floor/level number (0=town, 1-16=dungeon)
- `ME=34,18,72,33` - Companion: x, y, hp%, mp%
- `PLYR=51,54` - Main player position (x, y)
- `M=id@x,y,hp%,flags;...` - Monsters (semicolon-separated)
  - flags: bit 0=hostile, bit 1=unique, bit 2=ranged
- `L=id@x,y,value;...` - Loot items (semicolon-separated)

### LLM Prompt Format (Generated by `dsl_parser.py`):
```
SUM ME=78,78 HP62 MP100 FL=1 PLYR=77,77 dist=2 NEAR: 38@79,78:100%^0 164@78,88:100%^0 LOOT: 27@77,74:14
RISK=low SAFE_TILE=77,77
GOAL explore floor_1
MEM visited visited visited
```

**Risk Signals**:
- `RISK=high/med/low` - Calculated from HP% and monster count
- `SAFE_TILE=x,y` - Main player position (retreat target)
- `BEST_LOOT=id@x,y:value` - Highest value item nearby

### DSL Command Format (Agent → Game):
```
MV 51 54    # Move to coordinates
AT 164      # Attack monster ID 164
PK 27       # Pick up item ID 27
SAY Hello   # Chat message
```

This compact format gives LLMs complete tactical context while using 5x fewer tokens than JSON!

## Key Implementation Details
- **Socket**: `/tmp/devilutionx-gap.sock`
- **Build**: `-DENABLE_GAP=ON` compile flag
- **Pathfinding**: `MakePlrPath()` + `NetSendCmdLoc()`
- **Player ID**: `MyPlayerId >= MAX_PLRS` (unsigned)

### MCP Agent Architecture:
```
┌─────────────┐    GAP Socket    ┌─────────────┐    HTTP API    ┌─────────────┐
│   Diablo    │◄────────────────►│ MCP Server  │◄──────────────►│   Ollama    │
│   (GAP)     │   JSON Messages  │ (Bridge)    │  Natural Lang  │  (LLM GPU)  │
└─────────────┘                  └─────────────┘                └─────────────┘
                                        │
                                        ▼
                                 ┌─────────────┐
                                 │   Claude    │
                                 │ Code (MCP)  │
                                 └─────────────┘
```

**Key Components:**
- **MCP Server**: Bridges GAP socket ↔ Ollama API  
- **State Translator**: Game state → Natural language context
- **Intent Parser**: LLM decisions → GAP intents
- **Context Manager**: Maintain game session memory
- **Prompt Templates**: Personality system & tactical guidance

**Implementation Location**: `tools/gap/` directory for MCP server, prompts, and LLM integration tooling.

### Testing & Known Issues
- **Test agents**: See `tools/gap/` directory
- **Known limitations**: Complex pathfinding struggles, spell casting not implemented
- **Performance**: Varies by LLM model (qwen2.5:3b recommended)

## Architectural Approaches

### Companion Mode (POC Complete, Architecture Redesign Needed) ⚠️
- **Concept**: Load saved character into multiplayer slot
- **POC Success**: Chat, LLM decisions, combat AI, navigation all proven working
- **Critical Bug**: Commands execute on wrong player due to network routing assumptions
- **Root Cause**: GAP was bolted onto single-player control; needs proper entity control abstraction

### Headless Peer Mode (Future)
- **Concept**: Two separate game instances via TCP/IP
- **Benefits**: Natural multiplayer, independent saves
- **Status**: Planning phase

### POC Evaluation Summary (Sept 2025)
- ✅ **JSON Communication**: Fixed truncation with `num_predict: 200`
- ✅ **LLM Integration**: Combat decisions, navigation, chat all working  
- ✅ **Multi-Tech Stack**: DevilutionX ↔ GAP ↔ MCP ↔ Ollama successfully integrated
- ✅ **AI Behavior**: Threat assessment, combat priorities, survival reflexes functional
- ❌ **Architecture Limitation**: Network routing sends companion commands to wrong player
- **Lesson Learned**: Need proper entity control abstraction for scalable companion system

## Recent Protocol Enhancements

### Phase 0 Complete ✅ 
- **Intent Types**: `cast`, `pickup`, `use_potion`, `interact`, `path`, `explore`
- **State Additions**: Belt info, spells, objects, exploration data
- **Chat System**: Bidirectional LLM-powered conversation
- **Safety Systems**: Python survival reflexes, emergency healing
- **Navigation**: A* pathfinding with stuck detection

### Chat Commands:
- `!ai help` - Show commands
- `!ai status` - Display state  
- `!ai debug` - Debug info

## Recent Updates

### Enhanced Combat & AI Integration (Dec 2024) ✅
- **Wired Navigation & Survival Systems**: Integrated `navigation.py` and `survival_reflexes.py` into `mcp_server.py`
- **Combat Priority System**: Added smart target prioritization (low HP + close distance = high priority)
- **Enhanced Combat Prompts**: Crystal clear attack guidance with threat levels ("ATTACK_NOW", "ATTACK", "IGNORE")
- **Survival Override**: Emergency healing (<25% HP) and kiting (4+ enemies) override LLM decisions
- **A* Pathfinding**: NavigationPlanner enhances LLM movement with robust obstacle avoidance
- **Python Environment**: Fixed `setup.sh` and `pyproject.toml` for proper uv/venv compatibility

### Chat Separation (Sept 2025)
- Separated chat messages from state payloads
- Reduced JSON size by ~30%
- Instant chat responses without state bundling

## Agent Architecture Best Practices

### Character Profile Pattern (Recommended)

**Problem**: Agents see raw stats (`S=20,38,15,20,2,0,1,3423`) but lack identity and role awareness. They don't understand "I'm a **warrior** so I prefer swords over bows" or "I'm a **rogue** so I should kite rather than tank."

**Solution**: Initialize a `CharacterProfile` object on handshake from the first game state. This gives agents self-awareness about their class, role, playstyle, and equipment preferences.

**Benefits**:
- ✅ **Class-Appropriate Decisions**: Warriors prefer melee weapons, rogues prefer bows, sorcerers manage mana
- ✅ **Smart Loot Evaluation**: Keep gear that matches character build, skip inappropriate items
- ✅ **Context-Aware Shopping**: Buy heavy armor for warriors, light armor for rogues, staffs for sorcerers
- ✅ **Enhanced Chat**: Companion talks with character identity ("I'm a level 3 Rogue with 4 HP potions ready!")
- ✅ **Combat Tactics**: Melee classes rush in, ranged classes kite, casters manage positioning

**Implementation Pattern**:
```python
# On first valid state (orchestrator initialization)
if self.profile is None and state.get("stats"):
    self.profile = CharacterProfile(state)

    # Inject profile into all agents
    for agent in self.agents:
        agent.profile = self.profile

    # Inject into chat handler
    self.chat_handler.profile = self.profile

# In agents - use profile for decisions
if self.profile.should_keep_item("bw", "magic"):
    # Warrior: False ("bows aren't my thing")
    # Rogue: True ("bows are my specialty")

# For combat tactics
combat_context = self.profile.get_combat_context()
# Warrior: "MELEE FIGHTER - Get close, tank damage"
# Rogue: "RANGED ATTACKER - Keep distance, kite enemies"
```

**Example Profile Output**:
```
👤 Character Profile Created
   Class: Rogue (level 2)
   Role: Ranged DPS - high DEX, bow damage, hit-and-run tactics
   Playstyle: ranged_dps
   Stats: STR=20 DEX=38 MAG=15 VIT=20
   Preferred weapons: bw
   Preferred armor: la
```

**Real-World Impact**:
- Warrior finding magic bow → "You should take this, I'm better with swords"
- Rogue near healer → Buys HP potions (not mana - not a caster)
- Sorcerer in combat → Stays at range, manages mana vs. warriors who rush in

**Reference Implementation**: See `CHARACTER-PROFILE-SYSTEM.md` and `tools/gap/character_profile.py` (350 lines)

**Status**: ✅ Implemented (Nov 2025) - Recommended pattern for all GAP agents

## Development Environment

### Quick Setup:
```bash
cd tools/gap
./setup.sh              # Auto-setup with uv or traditional venv
./dev.sh run mypassword  # Run enhanced MCP server  
./dev.sh test           # Validate all systems
```

### Development Commands:
- `./dev.sh run [password]` - Run enhanced MCP server
- `./dev.sh combat [password]` - Run combat agent
- `./dev.sh test` - Run validation tests
- `./dev.sh format` - Format code with black
- `./dev.sh lint` - Check code with ruff
- `./dev.sh clean` - Clean logs and cache

### Enhanced AI Features:
- ⚔️ **Aggressive Combat**: AI prioritizes combat over exploration
- 🎯 **Smart Targeting**: Low HP enemies first, threat-based prioritization  
- 🚨 **Survival Reflexes**: Emergency healing and kiting override LLM
- 🧭 **A* Navigation**: Robust pathfinding with waypoint chunking
- 💬 **Natural Chat**: Bidirectional conversation with context awareness

## Combat Debug Investigation History

### Sept 2025: Command Routing Bug Identified ✅
**Issue**: Companion AI generates correct intents but commands execute on wrong player
**Root Cause**: GAP architecture evolved from single-player to companion mode without updating network command routing

**Debug Evidence**:
```
GAP: GetControlledPlayer - controlled_slot=1 MyPlayerId=
GAP: ExecuteMove - Controlling player 1 (name: Rodney) at pos (2,/) to target (53,44)
⚔️ SENDING TO LLM: 5 monsters, priority target: ID 7 Skeleton (Action: ATTACK_NOW)
🔍 RAW OLLAMA RESPONSE: {"intent": {"type": "intent", "action": "attack", "params": {"x": 76, "y": -1}}}
```

**Architecture Issue**:
- ✅ `GetControlledPlayer()` correctly returns slot 1 (companion)
- ✅ LLM generates valid attack intents for companion
- ❌ `NetSendCmdLoc(companion_id, ...)` routes commands to main player instead of companion
- **Fix needed**: Update GAP network command routing for proper player slot isolation

### Dec 2024: Monster Visibility Investigation ✅ (RESOLVED)
**Issue**: Companion not detecting monsters (resolved - was AI processing bug)
**Solution**: Enhanced debug logging revealed companion receives full monster data correctly

## Next Architecture: First-Class Entity Control System

### Problem with Current Architecture
- GAP was designed for single-player AI control (AI controls main player)
- Companion mode was bolted on using multiplayer slots
- Network command routing assumes single player context
- Results in commands executing on wrong player

### Proposed Solution: Entity Controller Abstraction
```
Human Input    → EntityController[0] → Player 0 Actions
GAP Protocol   → EntityController[1] → Player 1 Actions  
GAP Protocol   → EntityController[2] → Player 2 Actions
GAP Protocol   → EntityController[3] → Player 3 Actions
```

### Benefits
- **Clean separation**: Each entity has its own control interface
- **Scalable**: Support 1→3+ companions without architectural changes  
- **No network hacks**: Direct entity manipulation instead of fighting multiplayer routing
- **Diablo 2 style**: Similar to mercenary/hireling system
- **Future-proof**: Supports different control types (human, AI, scripted)

### Implementation Notes
- Create `EntityController` abstract interface
- `HumanController` for keyboard/mouse input
- `GapAIController` for LLM/GAP protocol
- `EntityManager` to coordinate all controllers
- Direct player state manipulation without network commands

## Critical Design Principle: Companions as First-Class Players ⚡

**FUNDAMENTAL RULE**: AI companions must be indistinguishable from real players to the game engine. Never create special case logic - instead, ensure companions follow the same initialization and systems as human players.

### ✅ Success Story: Universal Damage System (Sept 2025)
**Problem**: Companions made hit sounds but took no damage due to engine restricting damage to `MyPlayerId` only.

**Wrong Approach**: Patch compilation flags, add GAP-specific conditions
**Correct Solution**: Remove player ID restriction entirely - ALL players take damage from monster attacks

```cpp
// ❌ BAD: Special cases and restrictions  
if (player.getId() == MyPlayerId) {
    ApplyPlrDamage(...);  // Only human player
}
#ifdef ENABLE_GAP
else if (gap::IsCompanion(player.getId())) {
    ApplyPlrDamage(...);  // Special companion case
}
#endif

// ✅ GOOD: Universal behavior
// Apply damage to any valid player in the game (multiplayer-like behavior)
ApplyPlrDamage(DamageType::Physical, player, 0, 0, dam);
```

**Result**: Companions now take damage exactly like real players, no special handling required.

### Design Guidelines
1. **No Special Cases**: If you're writing `#ifdef ENABLE_GAP` to handle companion behavior differently, you're probably doing it wrong
2. **Multiplayer Parity**: Ask "How does this work for player 2 in real multiplayer?" and make companions work the same way
3. **Universal Systems**: Engine systems should work for ANY player, not just `MyPlayerId`
4. **Proper Initialization**: Ensure companions go through same player initialization as joining multiplayer players

### Code Review Questions
- Does this code treat companions differently than multiplayer players?
- Would this work if player 2 joined a multiplayer game?
- Are we adding complexity instead of removing restrictions?
- Is the engine properly recognizing the companion as a valid player entity?

## Technical Debt
- ~~**PRIORITY: Implement first-class entity control system**~~ ✅ Fixed with universal damage system
- Replace custom JSON with nlohmann/json
- Add GAP config file  
- Implement state delta compression
- ~~Fix MCP server movement bug~~ ✅ Fixed with navigation integration
- ~~Fix JSON truncation in LLM responses~~ ✅ Fixed with `num_predict: 200`
- ~~Investigate GAP companion monster visibility~~ ✅ Resolved - monsters visible to companion

## Python

when working with python, use unix line endings, not windows.
