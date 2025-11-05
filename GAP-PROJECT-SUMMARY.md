# GAP Project: LLM-Powered AI Companion for Diablo

## Executive Summary

**What is this?** An autonomous AI companion for Diablo 1 that uses Large Language Models (LLMs) to make tactical decisions, cooperate with human players, and learn from experience.

**Why is this unique?** Unlike scripted game AI or chatbots, this is a **full agent** that sees the game world, makes real-time tactical decisions, has persistent memory, and plays cooperatively with humans - all powered by natural language reasoning.

**Tech Stack:**
- **Game Engine:** DevilutionX (open-source Diablo 1 engine)
- **Protocol:** Custom DSL over Unix socket IPC
- **AI Backend:** Ollama (local LLM inference on NVIDIA GPU)
- **Agent Architecture:** Multi-agent council system with specialized experts
- **Memory:** SQLite-based persistent spatial/goal memory
- **Language:** C++ (game hooks), Python (agent logic)

**Development Timeline:** ~15 hours over 2 days (after previous monolithic approach failed)

---

## Technical Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Human Player + Diablo Game                   │
│                         (DevilutionX)                            │
└────────────────────────────┬────────────────────────────────────┘
                             │ Unix Socket IPC
                             │ (DSL Protocol)
┌────────────────────────────┴────────────────────────────────────┐
│                  Multi-Agent Orchestrator                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  Combat  │  │ Movement │  │   Loot   │  │  Healing │  ...  │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│       │             │              │              │             │
│       └─────────────┴──────────────┴──────────────┘             │
│                     Weighted Voting                             │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP API
                             │
┌────────────────────────────┴────────────────────────────────────┐
│                    Ollama (LLM Inference)                        │
│              qwen2.5:3b / llama3.1:8b / etc.                    │
│                   Running on NVIDIA GPU                          │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Architecture Works

**Multi-Agent Council vs Monolithic LLM:**
- **Problem with monolithic:** Single LLM trying to handle all decisions → confused priorities, token bloat, slow
- **Solution:** Specialized agents with narrow domains → each expert votes on their specialty
- **Result:** 5x faster decisions (500ms-2s → 200-500ms), 5x fewer tokens (400-600 → 80-120)

**Agent Specialization:**
- **Combat Agent:** Target selection, ranged positioning, threat assessment
- **Movement Agent:** Exploration, pathfinding, following player
- **Loot Agent:** Item prioritization, inventory management
- **Healing Agent:** HP monitoring, potion usage, town portal decisions
- **Shopping Agent:** Buy supplies based on class needs
- **Chat Agent:** Natural conversation, context-aware responses

**Weighted Voting System:**
```python
# Each agent proposes action + confidence weight
Combat:   "AT 142 (weight: 0.90)"  → score: 7.35
Healing:  "NONE (weight: 0.0)"     → score: 0.0
Movement: "MV 75 82 (weight: 0.45)" → score: 3.15

# Highest score wins
Winner: Combat agent attacks monster 142
```

---

## Protocol Design: DSL over JSON

### Evolution: Why DSL?

**Initial Approach (JSON):**
```json
{
  "tick": 12345,
  "floor": 1,
  "player": {"x": 34, "y": 18, "hp": 72, "mp": 33},
  "monsters": [
    {"id": 12, "x": 38, "y": 16, "hp": 55, "flags": 1},
    {"id": 19, "x": 36, "y": 17, "hp": 20, "flags": 1}
  ],
  "loot": [...]
}
```
**Problems:**
- 1-2KB per message
- 400-600 tokens per LLM call
- Verbose, slow parsing

**Current Approach (DSL):**
```
T=12345 F=1 ME=34,18,72,33 M=12@38,16,55,1;19@36,17,20,1 L=71@35,19,10
```
**Benefits:**
- 100-200 bytes per message (10x smaller)
- 80-120 tokens per LLM call (5x fewer)
- Human-readable, easy to parse
- Grammar-constrained output (GBNF forces valid commands)

### DSL Command Reference

```
# Movement
MV x y              # Move to coordinates

# Combat
AT x y              # Attack position (ranged - no pathfinding)
AT id               # Attack monster ID (melee - paths to target)

# Items
PK id               # Pick up item

# Communication
SAY message         # Chat with human player

# Future: Spell casting
CAST spell_id id    # Cast spell at monster
CAST spell_id x y   # Cast spell at position (AoE)
```

### Design Philosophy

**Flat namespace, not tree structure:**
- Simple for LLMs to learn
- Easy to parse (match first token)
- Python handles tactics, DSL handles instructions
- C++ executes faithfully

**Why not `COMBAT.ATTACK.RANGED`?**
- Over-engineered for LLM bridge
- Harder to parse and validate
- Duplicates logic across layers
- Flat is more maintainable

---

## Key Technical Innovations

### 1. Character Profile System

**Problem:** Agent sees raw stats (`S=20,38,15,20`) but doesn't understand "I'm a Rogue, so I kite with a bow"

**Solution:** Initialize `CharacterProfile` from first game state
```python
profile = CharacterProfile(initial_state)
# Class: Rogue (level 2)
# Role: Ranged DPS - high DEX, bow damage, hit-and-run tactics
# Playstyle: ranged_dps
# Stats: STR=20 DEX=38 MAG=15 VIT=20
# Preferred weapons: bw (bows)
# Preferred armor: la (light armor)
```

**Impact:**
- Combat agent knows to maintain distance and kite
- Loot agent keeps bows, rejects swords
- Shopping agent prioritizes HP potions over mana
- Chat agent talks with class identity

### 2. Ranged Combat Positioning

**Problem:** Rogue with bow was running into melee range (face-tanking)

**Root Cause:** `AT <id>` commands trigger pathfinding to monster (melee behavior)

**Solution:** Position-based attacks for ranged characters
```python
if combat_style == "ranged":
    if 4 <= distance <= 10:
        # Good range - attack without moving
        command = f"AT {monster_x} {monster_y}"  # Position attack
    elif distance < 4:
        # Too close - kite away
        command = f"MV {retreat_x} {retreat_y}"
    else:
        # Too far - move closer
        command = f"MV {approach_x} {approach_y}"
```

**DSL Extension:**
```cpp
// Dual-format attack parsing
AT <id>     → Attack monster (paths to target, melee)
AT <x> <y>  → Attack position (no pathfinding, ranged)
```

**Result:** Rogue maintains 4-10 tile distance, shoots from safety

### 3. Companion Entity Control

**Critical Design Principle:** Companions must be indistinguishable from real multiplayer players

**Problem:** Commands routed through network layer assumed main player context

**Solution:** Direct execution for companions
```cpp
if (controlled_id != MyPlayerId) {
    // Companion - use direct execution
    ExecuteDirectAttack(companion_id, monster_id);
} else {
    // Main player - use network commands
    NetSendCmdParam1(CMD_ATTACKID, monster_id);
}
```

**Universal Damage System:**
```cpp
// ❌ BAD: Special cases
if (player.getId() == MyPlayerId) {
    ApplyPlrDamage(...);  // Only human
}

// ✅ GOOD: Universal behavior
ApplyPlrDamage(DamageType::Physical, player, 0, 0, dam);
// Works for any valid player (multiplayer-like)
```

### 4. SQLite Persistent Memory

**Problem:** LLMs are stateless - forget goals, visited rooms, strategies

**Solution:** Memory store with spatial/goal tracking
```python
memory.remember_location(x, y, "shrine_of_strength", floor=1)
memory.set_goal("find_stairs_down")
memory.query_spatial(x, y, radius=20)  # "You've been here before"
```

**Use Cases:**
- Remember shrine locations for later visits
- Track explored vs unexplored areas
- Recall quest objectives across sessions
- Learn from deaths ("Butcher killed me last time - be careful")

### 5. Character-Specific Personality Persistence

**Problem:** AI companions should remember experiences and grow across sessions - but each character should have distinct memories

**Solution:** SQLite personality database with character-scoped memories

**Character Identity Format:**
```
Rogue level 5    → "Rogue_5"
Warrior level 3  → "Warrior_3"
Sorcerer level 12 → "Sorcerer_12"
```

**What Gets Remembered (Per Character):**
```python
# Episodic memories with emotional impact
personality.add_memory(
    "death",
    "Killed by Butcher on level 2",
    emotional_impact=-0.9,
    location="level_2",
    actor="Butcher"
)

# Learned strategies with success tracking
personality.add_strategy(
    "facing_butcher",
    "retreat_to_stairs",
    success=True  # 2 wins, 0 losses = 100% confidence
)

# Evolving personality traits
personality.update_trait(
    "risk_tolerance",
    "cautious",
    confidence=0.8,
    context="Nearly died to Butcher in first session"
)
```

**Database Schema (5 Tables):**
- **personality_traits**: Evolving traits per character (risk_tolerance, player_relationship)
- **memories**: Episodic events with emotional impact (-1.0 to +1.0)
- **learned_strategies**: Success/failure tracking with confidence scores
- **prompt_injections**: Dynamic context for agent decisions
- **session_reflections**: LLM-generated end-of-session summaries

**Key Feature: Character Isolation**

Each companion character maintains completely separate memories:
- Your **Rogue_5** remembers kiting tactics, bow gifts from player, cautious playstyle
- Your **Warrior_3** remembers face-tanking failures, close calls, aggressive tactics
- Your **Sorcerer_8** starts fresh, builds own magical combat memories

**Why This Matters:**
- **Realistic:** Just like each save file is separate, each character's personality is unique
- **Class-appropriate:** Rogue learns ranged tactics, Warrior learns melee strategies
- **Relationship tracking:** Player's generosity to one character doesn't affect another
- **Multiple playthroughs:** Run 3 different characters, each with distinct personalities

**Example Session Flow:**
```bash
# Play as Rogue companion
python3 orchestrator.py  # Detects "Rogue_5", loads Rogue memories
# ... gameplay ...
# Ctrl+C: "Learned to keep distance. Player shared potions."

# Later, play as Warrior companion
python3 orchestrator.py  # Detects "Warrior_3", loads Warrior memories
# ... gameplay ...
# Ctrl+C: "Tanking works better with shield. Need more HP potions."

# View Rogue's memories only
python3 view_personality.py gap_personality.db Rogue_5
```

**Graceful Shutdown:**
On Ctrl+C, the orchestrator:
1. Generates LLM reflection on the session
2. Saves all memories/traits for that character
3. Closes database cleanly

**Chat Integration:**
Companion responses reference recent memories:
- After Butcher death: "I'm being careful after that Butcher incident"
- After player gift: "Thanks! You've been generous with potions today"
- Context-aware personality: Cautious Rogue vs Aggressive Warrior

### 6. Grammar-Constrained Output (GBNF)

**Problem:** LLMs sometimes hallucinate invalid commands

**Solution:** Force valid DSL with grammar constraints
```
root   ::= (move | attack | pickup | none) "\n"?
move   ::= "MV " int " " int " " weight
attack ::= "AT " int (" " int)? " " weight
pickup ::= "PK " int " " weight
none   ::= "NONE " weight
weight ::= "0." digit+ | "1.0"
int    ::= digit+
digit  ::= [0-9]
```

**Result:** LLM cannot output invalid syntax - guaranteed parseable commands

---

## Performance Metrics

### Decision Speed
- **Monolithic (failed attempt):** 2-5s per decision
- **Multi-agent (current):** 200-500ms per decision
- **Improvement:** 4-10x faster

### Token Usage
- **JSON protocol:** 400-600 tokens per state
- **DSL protocol:** 80-120 tokens per state
- **Improvement:** 5x reduction

### Memory Efficiency
- **JSON messages:** 1-2KB per state
- **DSL messages:** 100-200 bytes per state
- **Improvement:** 10x smaller

### LLM Resource Usage
- **Ollama on NVIDIA GPU:** ~4GB VRAM (qwen2.5:3b)
- **Game CPU usage:** Minimal impact (Diablo is mostly CPU, not GPU)
- **Result:** LLM and game coexist without performance degradation

### Recommended Models
- **qwen2.5:3b** - Fast, good tactical decisions (200-300ms)
- **llama3.2:latest** - Balanced speed/quality (400-500ms)
- **llama3.1:8b** - Best reasoning, slower (800-1200ms)

---

## Why Diablo 1 Was the Perfect Choice

### Technical Reasons
1. **Tile-based grid** - Easy coordinate parsing (x, y positions)
2. **Turn-based rhythm** - LLM has time to think (not twitch shooter)
3. **Rich strategy space** - Combat, inventory, shopping, spells, teamwork
4. **Open source engine** - DevilutionX allows deep integration
5. **Multiplayer architecture** - Already has slots for companion entities
6. **CPU-bound game** - GPU free for LLM inference (zero performance impact)

### Why Not Modern Games?
- **3D vision** - Expensive to parse, harder to reason about
- **Real-time action** - Frame-perfect timing (LLMs too slow)
- **Complex physics** - Harder for LLM to model/predict
- **Closed source** - Can't inject protocol hooks
- **GPU contention** - Modern games saturate GPU, fight with LLM

### Strategic Advantages
- **Contained environment** - Finite state space for LLM to learn
- **Clear objectives** - Kill monsters, find loot, descend levels
- **Cooperative design** - Already built for human teams
- **Emergent complexity** - Simple rules → complex tactics

---

## Real-World Behavior Examples

### Ranged Combat (Rogue with Bow)
```
[Agent sees 3 monsters at various distances]

Combat Agent LLM reasoning:
"Monster 132 is an archer at 4 tiles - good bow range.
 Monster 88 is melee at 2 tiles - too close, need to kite.
 Monster 142 is at 6 tiles - perfect range."

Decision sequence:
1. AT 72 80 (attack archer from distance 4) ✅
2. MV 69 82 (kite away from melee at 2 tiles) ✅
3. AT 71 77 (attack from distance 6) ✅

Result: Maintains optimal bow range, never face-tanks
```

### Inventory Management (Loot Agent)
```
[Found magic sword on ground]

Loot Agent: "I'm a Rogue (DEX-focused, prefers bows).
             Magic sword not my style - leaving for player."

[Found magic bow]

Loot Agent: "Magic bow! That's my weapon type - picking up!"
             PK 71
```

### Shopping Behavior (Shopping Agent)
```
[In town, low on HP potions]

Shopping Agent: "I'm a Rogue (ranged DPS).
                 Priority: HP potions > light armor > bows > scrolls
                 Current belt: 2/8 HP potions - need refill!"

Action: Buy 4 HP potions from Pepin
```

### Chat Integration
```
Human: "Ready for level 2?"

Chat Agent (with profile context):
"Yeah! I've got 6 HP potions and my bow is loaded.
 Let me scout ahead - I'm faster than you."

[After combat]
Chat Agent: "That was close! I'm at 40% HP, heading back to town."
```

### Personality Persistence (Character-Specific)
```
[Playing as Rogue_5 companion - Session 1]
Orchestrator: "📚 PersonalityStore initialized for Rogue_5"
[Combat: Nearly dies to Butcher, survives at 15% HP]
Memory: "Won tough battle on floor 2 (lowest HP: 15%)" [impact: +0.7]

[Ctrl+C to exit]
Reflection: "Learned to keep distance from Butcher. Kiting works!"
✅ Shutdown complete. Personality saved.

[Playing as Warrior_3 companion - Session 1]
Orchestrator: "📚 PersonalityStore initialized for Warrior_3"
[Combat: Face-tanks Butcher, dies at level 2]
Memory: "Died in combat on floor 2" [impact: -0.9]

[Ctrl+C to exit]
Reflection: "Need better armor before facing unique monsters."
✅ Shutdown complete. Personality saved.

[Later: View database]
$ python3 view_personality.py gap_personality.db

🎭 CHARACTERS: Rogue_5, Warrior_3

[Rogue_5] Memories:
  😊 Won tough battle on floor 2 (lowest HP: 15%)
     Impact: +0.7 | Confidence building

[Warrior_3] Memories:
  💔 Died in combat on floor 2
     Impact: -0.9 | Learning from mistakes

[Playing as Rogue_5 again - Session 2]
Orchestrator: "📚 Loaded personality: 0 traits, 1 memory"
Chat Agent (referencing memory): "I remember that close call with Butcher..."
```

**Key Feature:** Each character maintains completely separate memories. Your Rogue doesn't remember your Warrior's death, and vice versa!

---

## Technical Challenges Solved

### Challenge 1: Command Routing Bug
**Problem:** Companion AI generated correct commands, but they executed on wrong player

**Investigation:**
```
Python: "AT 59" (attack monster 59)
C++:    "GetControlledPlayer() = 1 (companion)" ✅
C++:    "NetSendCmdParam1(CMD_ATTACKID, 59)"
Game:   *Main player attacks instead of companion* ❌
```

**Root Cause:** Network commands assumed `MyPlayerId` context, not companion slot

**Solution:** Direct execution path for companions
```cpp
if (controlled_id != MyPlayerId) {
    // Companion - bypass network, execute directly
    player.destAction = ACTION_ATTACKMON;
    player.destParam1 = monster_id;
    ClrPlrPath(player);
} else {
    // Main player - use network commands
    NetSendCmdParam1(CMD_ATTACKID, monster_id);
}
```

### Challenge 2: Position Attack Range Errors
**Problem:** Agent sending `AT x y` but getting "Monster out of range" errors

**Investigation:**
```
Python logs:
⚔️ RANGED: Attacking monster 132 at distance 4 without moving
📤 Command: AT 72 80

C++ logs:
GAP: Position attack → Direct attack on monster 132 at (72,80) ✅

Python logs (different monster):
⚔️ RANGED: Closing distance to monster 59 (currently 11 tiles)
📤 Command: AT 59

C++ logs:
GAP: ExecuteDirectAttack - Monster 59 out of range ❌
```

**Root Cause:** For monsters >10 tiles, Python sent `AT <id>` (expecting C++ to close distance), but `ExecuteDirectAttack` has 15-tile hard limit

**Solution:** Python uses movement commands for distant monsters
```python
if distance > 10:
    # Calculate position 8 tiles from monster
    approach_x = mob_x + (direction_x * 8)
    approach_y = mob_y + (direction_y * 8)
    command = f"MV {approach_x} {approach_y}"  # Move first
else:
    command = f"AT {mob_x} {mob_y}"  # Attack directly
```

### Challenge 3: JSON Truncation
**Problem:** LLM responses getting cut off mid-JSON

**Root Cause:** Default `num_predict: 128` too short for JSON responses

**Solution:** Increase token limit + switch to DSL
```python
# Ollama config
"num_predict": 200  # Was 128

# Better: Use DSL (only needs ~30 tokens)
"AT 142 0.90\n"  # vs JSON: {"intent": {"type": "attack", ...}}
```

---

## What's LLM vs What's Code?

**Important Clarification:** This is NOT "pure LLM plays game" - it's a **hybrid architecture** where each layer does what it's best at.

### ✅ LLM-Powered (Natural Language Reasoning)

**Decision Making:**
- ✅ **Combat target selection** - "Monster 142 has low HP and is close → attack first"
- ✅ **Chat responses** - "I've got 6 HP potions ready" (context-aware conversation)
- ✅ **Shopping decisions** - "I'm a Rogue, need HP potions more than mana"
- ✅ **Item evaluation** - "Magic bow? That's my weapon type!" (via profile prompts)

**What LLM sees:**
```
SUM ME=78,78 HP62 MP100 FL=1 PLYR=77,77 dist=2
NEAR: 38@79,78:100%^0 164@78,88:100%^0
LOOT: 27@77,74:14
GOAL explore floor_1
```

**What LLM outputs:**
```
AT 164 0.85  # Attack monster 164, confidence 85%
```

### 🐍 Python Logic (Deterministic, Fast)

**Tactical Execution:**
- ✅ **Ranged positioning** - "Distance=4 → good bow range, attack without moving"
- ✅ **Emergency healing** - "HP<25% → use potion NOW" (overrides LLM)
- ✅ **Kiting logic** - "Distance<4 → calculate retreat vector away from threat"
- ✅ **Survival reflexes** - "4+ enemies → retreat to safe position"
- ✅ **Equipment repair detection** - "Durability<75% → go to Griswold"
- ✅ **Item stat comparison** - "New bow: 7.2 score vs old bow: 4.95 score → upgrade"

**Why Python for these?**
- **Speed:** Instant decisions (no LLM latency)
- **Reliability:** No hallucinations, guaranteed correct math
- **Cost:** Free CPU cycles vs LLM token cost
- **Safety:** Critical survival logic can't be overridden by confused LLM

### ⚙️ C++ Game Engine (Pure Execution)

**No AI Here:**
- ✅ Pathfinding (A* algorithm)
- ✅ Combat calculations (damage, AC, ToHit)
- ✅ Network commands (multiplayer routing)
- ✅ Item management (inventory, equipment)
- ✅ Animation and rendering

**Philosophy:** C++ just executes DSL commands faithfully, no decision-making.

### 🧠 The Hybrid Advantage

```
Human: "There's 3 monsters coming!"

Python:  Detects HP<30%, 3+ enemies → OVERRIDE: retreat (instant)
         ↓
LLM:     Gets simplified state: "Low HP, unsafe" → agrees to retreat
         ↓
C++:     Executes MV command → character runs to safety
         ↓
Chat LLM: "Oof! Retreating, need healing!" (natural response)
```

**Why this works:**
1. **Python handles life-or-death** (no time for LLM to "think")
2. **LLM handles strategy** (target priority, shopping, chat)
3. **C++ handles execution** (faithful command interpreter)

**Result:** Fast reflexes + smart decisions + reliable execution

---

## TODO: Feature Gaps

### 🔴 High Priority (Core Gameplay Loop)

**Equipment Upgrade System:**
- [ ] **UpgradeAgent** - Use ItemComparator to find better equipment in inventory
- [ ] **EQUIP command** (C++) - Swap inventory item to equipment slot
- [ ] **Sell-after-upgrade** - Mark replaced gear for Griswold to sell
- **Impact:** Complete identify→compare→equip→sell cycle
- **Effort:** ~2 hours (mostly plumbing)

**Cain Identification Loop:**
- [ ] **Multi-item identification** - Identify all unidentified items, not just first
- [ ] **Priority sorting** - Identify class-appropriate items first
- **Impact:** Companions fully utilize magic/unique drops
- **Effort:** 30 minutes (extend existing CainAgent)

### 🟡 Medium Priority (Quality of Life)

**Dungeon Objects:**
- [ ] **Chest interaction** - Detect chests, open them safely (check for ambushes)
- [ ] **Barrel breaking** - Smash barrels for extra loot/spawns
- [ ] **Shrine usage** - Evaluate shrine risks vs benefits
- **Impact:** More thorough dungeon exploration
- **Effort:** ~2 hours (object detection in DSL + agent logic)

**Economic Intelligence:**
- [ ] **Gold budgeting** - Track gold, prioritize essential vs luxury purchases
- [ ] **Value assessment** - Know when to sell vs save items
- [ ] **Opportunity cost** - "Save gold for better gear at Griswold vs buy potions now"
- **Impact:** Smarter resource management
- **Effort:** ~3 hours (economic model + shopping priorities)

**Multi-Enemy Tactics:**
- [ ] **Formation detection** - Identify clustered vs scattered enemies
- [ ] **AoE opportunity** - "5 enemies grouped → Fireball worth it"
- [ ] **Focus fire coordination** - "Attack same target as player"
- **Impact:** More efficient combat, better teamwork
- **Effort:** ~2 hours (threat clustering in combat agent)

### 🟢 Low Priority (Polish & Advanced)

**Learning from Deaths:**
- [ ] **Death memory** - Remember "Butcher killed me → retreat next time"
- [ ] **Danger zones** - Track high-risk areas by floor/monster type
- [ ] **Strategy adaptation** - "Last approach failed → try different tactic"
- **Impact:** Companion gets smarter over time
- **Effort:** ~4 hours (memory schema + retrieval in agents)

**Personality Profiles:**
- [ ] **Aggressive vs Cautious** - Different risk tolerances
- [ ] **Greedy vs Generous** - Item sharing behavior
- [ ] **Chatty vs Silent** - Conversation frequency
- **Impact:** Replay value, player preference matching
- **Effort:** ~2 hours (prompt templates + config)

**Stat Point Allocation:**
- [ ] **Level-up decisions** - Auto-allocate points based on class build
- [ ] **Build awareness** - "I'm a bow Rogue → prioritize DEX"
- **Impact:** Long-term character progression
- **Effort:** ~1 hour (simple heuristics by class)

### 🔵 Future Vision (Requires Architecture Changes)

**Multiple Companions:**
- [ ] **N-player support** - Party of 2-3 AI companions
- [ ] **Role assignment** - Tank + DPS + Support composition
- [ ] **Coordination** - "Tank pulls, DPS focuses fire, Support heals"
- **Impact:** Full party experience, emergent team tactics
- **Effort:** ~8 hours (multi-agent communication, conflict resolution)

**Voice Integration:**
- [ ] **Text-to-Speech** - Companion speaks in-game
- [ ] **Speech-to-Text** - Voice chat with companion
- [ ] **Emotion synthesis** - Tone changes based on game state
- **Impact:** Immersive AI teammate
- **Effort:** ~6 hours (TTS/STT integration, audio pipeline)

**Cross-Run Memory:**
- [ ] **Session persistence** - Remember across game restarts
- [ ] **Player relationship** - Builds rapport over multiple runs
- [ ] **World knowledge** - "I remember that chest was trapped"
- **Impact:** Long-term companion relationship
- **Effort:** ~4 hours (extended memory schema)

---

## Future Enhancements (Original List - See TODO Above for Prioritized)

### Immediate Next Steps
- [x] ~~Spell casting system~~ ✅ DONE (Nov 2025)
- [x] ~~Equipment durability tracking~~ ✅ DONE (Nov 2025)
- [x] ~~Auto-repair at Griswold~~ ✅ DONE (Nov 2025)
- [x] ~~Item stat comparison~~ ✅ DONE (ItemComparator, Nov 2025)
- [ ] Equipment upgrade workflow (UpgradeAgent + EQUIP command)
- [ ] Gold tracking and economic decisions
- [ ] Multi-enemy threat prioritization

### Advanced Features
- [ ] Learning from deaths (memory store: "Butcher → retreat strategy")
- [ ] Coordinated tactics with player ("I'll kite while you tank")
- [ ] Personality system (aggressive vs cautious companion)
- [ ] Multiple companions with different classes/roles

### Long-Term Vision
- [ ] Party of 3 AI companions + human
- [ ] Companions remember previous runs
- [ ] Emergent team strategies
- [ ] Voice chat integration (TTS/STT)

---

## Lessons Learned

### Architectural Insights

1. **Multi-agent > Monolithic**
   - Specialized experts beat single generalist
   - Weighted voting enables graceful degradation
   - Easier to debug (isolated agent failures)

2. **DSL > JSON for LLM protocols**
   - 10x smaller messages
   - 5x fewer tokens
   - Grammar constraints prevent hallucination
   - Human-readable for debugging

3. **Python tactics, C++ execution**
   - Clear separation of concerns
   - Python iterates fast (no recompile)
   - C++ stays dumb (just executes commands)
   - LLM complexity lives in Python layer

4. **Character profiles enable identity**
   - Self-awareness transforms decision quality
   - Class-appropriate behavior emerges naturally
   - Chat becomes contextual and believable

5. **Companions as first-class players**
   - No special cases - treat like multiplayer
   - Universal systems work for any player entity
   - Direct execution for non-human players

### Development Process

1. **Failed monolithic attempt taught:**
   - Don't let LLM juggle too many concerns
   - Token count matters more than you think
   - Simplicity beats sophistication

2. **Multi-agent rebuild took 15 hours because:**
   - Clear mental model from failure
   - Focused scope (one agent at a time)
   - Incremental testing (combat first, then loot, etc.)

3. **Community/pair programming accelerates:**
   - Rubber duck debugging (explaining forces clarity)
   - Cross-domain knowledge (LLM + game engine + protocols)
   - Morale boost when stuck (persistence is key)

### Technical Wisdom

1. **Start with simplest thing that works**
   - Flat namespace > hierarchical DSL
   - Direct execution > complex routing
   - Hard-coded ranges > learned policies

2. **Separation of concerns is king**
   - Protocol layer (DSL)
   - Logic layer (Python agents)
   - Execution layer (C++ game hooks)
   - Memory layer (SQLite)

3. **Context matters more than intelligence**
   - Character profile > bigger LLM
   - Recent memory > perfect memory
   - Focused prompt > kitchen-sink prompt

4. **Debug visibility is critical**
   - Log everything (LLM reasoning, commands, execution)
   - Correlate across layers (Python → DSL → C++)
   - Timestamps catch timing bugs

---

## How to Use

### Quick Start
```bash
# 1. Start game with companion
cd /home/mental/projects/DevilutionX/build
./devilutionx --companion-save multi_1.sv --companion-slot 1

# 2. Start AI agent (in separate terminal)
cd /home/mental/projects/DevilutionX/tools/gap
python3 orchestrator.py --companion-slot 1 --model qwen2.5:3b --password "foo"

# 3. Play Diablo with your AI companion!
# - She'll follow you automatically
# - Fights enemies with class-appropriate tactics
# - Chats when you talk to her
# - Picks up loot intelligently
```

### Chat Commands
```
!ai help      # Show available commands
!ai status    # Display companion state
!ai debug     # Show debug information
```

### Configuration
Edit `tools/gap/orchestrator.py`:
- `--model` - LLM model (qwen2.5:3b, llama3.1:8b, etc.)
- `--companion-slot` - Player slot (1-3)
- Agent weights and priorities

---

## Why This Matters

### For Game Development
- **Emergent AI companions** - Not scripted, genuinely adaptive
- **Scalable to N companions** - Just spawn more slots
- **Personality as prompt** - Different companions = different prompts
- **Replay value** - Same content, different AI behavior each run

### For AI Research
- **Real-time agent systems** - Not batch prediction, actual gameplay
- **Multi-agent coordination** - Weighted voting, specialization
- **Memory and learning** - Persistent state across sessions
- **Tool use in games** - LLMs commanding game engines

### For You (Career)
- **Portfolio piece** - Demonstrates full-stack AI engineering
- **Novel application** - Not yet mainstream (early mover advantage)
- **Technical depth** - Protocol design, agent systems, game integration
- **Shareable demo** - YouTube + LinkedIn + GitHub showcase

---

## Next Steps for Showcase

### Content Creation
1. **YouTube Demo Video** (10-15 min)
   - Show side-by-side gameplay (human + AI companion)
   - Highlight tactical decisions (kiting, shopping, chat)
   - Walk through architecture diagram
   - Live coding segment (adding new agent?)

2. **LinkedIn Technical Post**
   - Lead with hook: "I taught an LLM to play Diablo cooperatively"
   - Architecture summary (multi-agent council)
   - Key innovations (DSL, character profiles, ranged combat)
   - Performance metrics (5x token reduction, 4x faster)
   - Call to action: "Interested in AI game companions? Let's connect!"

3. **GitHub Repository Polish**
   - README with architecture diagram
   - Quick start guide
   - API documentation (DSL reference)
   - Contributing guide (how to add new agents)
   - Video embed and screenshots

### Technical Polish Before Release
- [ ] Clean up debug logging (make it optional)
- [ ] Add config file (don't hardcode model/slot)
- [ ] Write unit tests for DSL parser
- [ ] Profile and optimize hot paths
- [ ] Document all agent interfaces
- [ ] Add example agent (template for extensions)

### Potential Impact
- **Game modding community** - Could become standard for Diablo mods
- **AI agent frameworks** - Reference implementation for game agents
- **Job opportunities** - Gaming AI, agent systems, LLM applications
- **Research citations** - Novel approach to LLM game integration

---

## Acknowledgments

**Development:** ~15 hours over 2 days (after failed monolithic attempt)

**Key Insight:** Multi-agent architecture emerged from analyzing monolithic failure

**Collaboration:** Pair programming with Claude Code (AI assistant) for debugging, architecture discussions, and implementation

**Inspiration:** Westworld (NPCs with memory), OpenAI Five (game agents), AutoGPT (tool use)

---

## Technical Specifications

### System Requirements
- **OS:** Linux (Unix sockets)
- **GPU:** NVIDIA with 4GB+ VRAM (for LLM inference)
- **RAM:** 8GB+ (game + LLM)
- **Storage:** 5GB (game + models)

### Software Stack
- **Game:** DevilutionX (commit: db37c41da)
- **LLM Runtime:** Ollama 0.1.x
- **Language:** C++17, Python 3.9+
- **Database:** SQLite 3
- **IPC:** Unix domain sockets (JSON + DSL)

### Build Instructions
```bash
# 1. Clone DevilutionX with GAP
git clone https://github.com/jstelzer/DevilutionX.git
cd DevilutionX
git checkout GAP

# 2. Build with GAP enabled
mkdir build && cd build
cmake .. -DENABLE_GAP=ON
cmake --build . --target devilutionx

# 3. Install Python dependencies
cd ../tools/gap
pip install -r requirements.txt

# 4. Install Ollama and download models
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b
ollama pull llama3.1:8b

# 5. Run!
./devilutionx --companion-save multi_1.sv --companion-slot 1
python3 orchestrator.py --companion-slot 1 --model qwen2.5:3b
```

---

## License & Attribution

**DevilutionX:** Sustainable Use License (original project)
**GAP Extensions:** [Your License] (your additions)

**Citation:**
```
GAP: Game Agent Protocol for LLM-Powered AI Companions
Author: [Jason Stelzer]
Year: 2025
Repository: [http://github.com/jstelzer/DevilutionX/]
```

---

## Contact & Links

- **GitHub:** [https://github.com/jstelzer]
- **LinkedIn:** [https://www.linkedin.com/in/jason-stelzer-9b5a422/]
- **YouTube:** [Demo Video]
- **Email:** [mental@neverlight.com]

---

*Last Updated: November 4, 2025*
*Version: 0.9 (Pre-release)*
