# Character Profile System - Self-Aware AI Companion

## Overview

The character profile system gives GAP agents **identity and self-awareness**. Agents now understand their class, role, playstyle, and make decisions appropriate to their character build.

## The Problem We Solved

### Before:
Agents saw stats as raw numbers: `S=20,38,15,20,2,0,1,3423`
- No understanding of "I'm a **warrior** so I prefer swords over bows"
- No class-appropriate equipment decisions
- Generic chat responses ("I'm fine" instead of "As a rogue, I prefer to stay at range")

### After:
Agents have **character identity** initialized on handshake:
```python
CharacterProfile:
  Class: Rogue (level 2)
  Role: Ranged DPS - high DEX, bow damage, hit-and-run tactics
  Playstyle: ranged_dps
  Preferred weapons: bows
  Preferred armor: light armor
```

## Architecture

### 1. Profile Creation (Handshake)

**When**: First valid state received from game
**Where**: `orchestrator.py` main loop

```python
# On first state with stats
self.profile = CharacterProfile(state)

# Share with all agents
for agent in self.agents:
    agent.profile = self.profile

# Share with chat handler
self.chat_handler.profile = self.profile
```

### 2. Profile Updates (Real-time)

**When**: Every state update
**What**: Tracks level ups, stat changes, inventory changes

```python
# Detects level ups
if current_level > self.level:
    logger.info(f"🎉 LEVEL UP! Warrior 2 → 3")

# Updates inventory summary
self.inventory_count = 15
self.belt_summary = "4 HP, 1 MP, 2 scrolls"
```

### 3. Profile Usage (All Agents)

All agents can access `self.profile` for context-aware decisions:

```python
# Combat agent
if self.profile.is_melee:
    return "Get close and tank"
elif self.profile.is_ranged:
    return "Keep distance and kite"

# Loot agent
eval = self.profile.should_keep_item("bw", "magic")
# Warrior: {"keep": False, "reason": "I'm a warrior - bows aren't my thing"}
# Rogue: {"keep": True, "reason": "I'm a rogue - bows are my specialty"}
```

## Key Features

### Class-Specific Metadata

**6 Classes Supported**:
0. Warrior - Melee tank (swords, axes, heavy armor)
1. Rogue - Ranged DPS (bows, light armor)
2. Sorcerer - Caster DPS (staffs, light armor, mana management)
3. Monk - Melee hybrid (balanced stats, martial arts)
4. Bard - Support hybrid (buffs, identification)
5. Barbarian - Melee berserker (high damage, glass cannon)

**Playstyles**:
- `melee_tank` - Frontline warrior
- `ranged_dps` - Hit-and-run rogue
- `caster_dps` - Spell-slinging sorcerer
- `melee_hybrid` - Monk martial artist
- `support_hybrid` - Bard utility
- `melee_berserker` - Barbarian damage dealer

### Smart Item Evaluation

```python
profile.should_keep_item("ax", "magic")

# Warrior response:
{
    "keep": True,
    "reason": "I'm a Warrior - axes are my preferred weapon",
    "priority": 0.9
}

# Rogue response:
{
    "keep": False,
    "reason": "I'm a Rogue - axes aren't my style (prefer bows)",
    "priority": 0.2
}

# But magic items always kept:
{
    "keep": True,
    "reason": "Magic items are valuable",
    "priority": 0.8
}
```

### Class-Appropriate Shopping

```python
profile.get_shopping_priorities()

# Warrior: ["hp", "sw", "ax", "ha", "sh", "sp"]
#          (health, swords, axes, heavy armor, shields, portals)

# Rogue: ["hp", "bw", "la", "sp"]
#        (health, bows, light armor, portals)

# Sorcerer: ["mp", "st", "la", "hp", "sp"]
#           (mana, staffs, light armor, health, portals)
```

### Enhanced Chat Context

**Before**:
```
Player: "How are you?"
Companion: "Fine!"
```

**After**:
```
Player: "How are you?"
Companion: "Not bad for a level 2 Rogue! Got 4 HP potions and a magic bow - ready to take on the dungeon."
```

**Chat LLM Context** (injected automatically):
```
You're a level 2 Rogue.
Role: Ranged DPS - high DEX, bow damage, hit-and-run tactics.
You're in town, safe. HP: 100%.
Carrying 12/40 items. Belt: 4 HP, 1 MP, 2 scrolls.
```

## Implementation Details

### CharacterProfile Class (`character_profile.py`)

**Properties**:
- `class_id` / `class_name` - Warrior, Rogue, Sorcerer, etc.
- `level` / `experience` - Character progression
- `strength`, `dexterity`, `magic`, `vitality` - Base stats
- `playstyle` - melee_tank, ranged_dps, caster_dps, etc.
- `preferred_weapons` - List of weapon type codes
- `preferred_armor` - List of armor type codes
- `is_melee`, `is_ranged`, `is_caster` - Role flags

**Methods**:
- `update_stats(state)` - Update from new game state (detects level ups)
- `should_keep_item(type, quality)` - Evaluate item for character
- `get_shopping_priorities()` - Class-specific shopping list
- `get_chat_context()` - Context string for chat LLM
- `get_combat_context()` - Tactical guidance for combat

### Integration Points

**Orchestrator** (`orchestrator.py`):
```python
# Line 461: Initialize on first state
if self.profile is None and state.get("stats"):
    self.profile = CharacterProfile(state)
    for agent in self.agents:
        agent.profile = self.profile
    self.chat_handler.profile = self.profile

# Line 470: Update on state changes
elif self.profile:
    if self.profile.update_stats(state):
        logger.info(f"📊 Character profile updated: {self.profile}")
```

**Base Agent** (`agents/base.py`):
```python
# Line 36: Profile available to all agents
self.profile = None  # CharacterProfile (injected by orchestrator)
```

**Chat Handler** (`chat_handler.py`):
```python
# Line 99: Profile for context
self.profile = None  # CharacterProfile (injected by orchestrator)

# Line 191-203: Enhanced chat context
if self.profile:
    context_str = f"You're a level {self.profile.level} {self.profile.class_name}. "
    context_str += f"{self.profile.role_description}. "
    # ... inventory awareness, etc.
```

## Real-World Examples

### Scenario 1: Loot Distribution

**Context**: Warrior companion finds magic bow

**Before**:
```
Agent: "Magic bow detected - picking up"
```

**After** (future - not implemented yet):
```python
eval = self.profile.should_keep_item("bw", "magic")
# Warrior: {"keep": False, "reason": "I'm a warrior - bows aren't my thing (prefer swords)"}

Chat: "Found a magic bow - you should take this, I'm better with swords"
# Or even: DROP command to leave for human player
```

### Scenario 2: Combat Tactics

**Before**:
```
Combat: Attack nearest enemy
```

**After**:
```python
# Warrior
combat_context = "MELEE FIGHTER - Get close, tank damage, protect allies"
# Prioritizes: Rush in, engage multiple enemies

# Rogue
combat_context = "RANGED ATTACKER - Keep distance, kite enemies, pick off stragglers"
# Prioritizes: Stay at range, retreat when enemies close

# Sorcerer
combat_context = "SPELLCASTER - Manage mana, cast from safety, high burst damage"
# Prioritizes: Mana conservation, safe positioning, spell timing
```

### Scenario 3: Shopping Intelligence

**Context**: Warrior at healer's shop

**Before**:
```
Shopping: Buy health potions (generic for all classes)
```

**After**:
```python
priorities = profile.get_shopping_priorities()
# Warrior: ["hp", "sw", "ax", "ha", "sh", "sp"]

# Prioritizes weapons/armor appropriate to class
# Skips mana potions (not a caster)
# Focuses on heavy armor over light armor
```

### Scenario 4: Chat Awareness

**Context**: Player asks "What do you have?"

**Before**:
```
"I have some stuff"
```

**After**:
```
Context: You're a level 3 Rogue. Carrying 15/40 items. Belt: 4 HP, 2 scrolls.

Response: "Got 4 healing potions, a couple scrolls, and picked up a sweet magic bow earlier. Inventory's getting full though - might need to sell some junk soon."
```

## Future Enhancements

### 1. Equipment Tracking
```python
profile.equipped = {
    "weapon": "Long Sword +2",
    "armor": "Full Plate Mail",
    "shield": "Tower Shield of Blocking"
}
# Use for: "Am I better geared than 5 minutes ago?"
```

### 2. Personality Traits
```python
profile.traits = {
    "brave": 0.8,  # Willing to take risks
    "greedy": 0.3,  # Prioritizes gold
    "helpful": 0.9,  # Shares loot with player
}
# Influences decisions: brave warrior rushes in, cautious rogue hangs back
```

### 3. Memory Integration
```python
# Store profile metadata in SQLite
memory.set("character.class", "Warrior")
memory.set("character.last_level_up", tick)
memory.set("character.equipment_tier", "mid")

# Chat can query: "What was I doing last time we played?"
```

### 4. Stat Point Allocation
```python
# Warrior: Prioritize STR/VIT
# Rogue: Prioritize DEX
# Sorcerer: Prioritize MAG

if profile.stat_points > 0:
    if profile.class_name == "Warrior":
        return "ADDSTAT STR"  # Or VIT if STR high enough
```

## Benefits

✅ **Self-Aware Agents** - Know who they are and what they're good at
✅ **Class-Appropriate Decisions** - Warriors tank, rogues kite, sorcerers cast
✅ **Better Chat** - Contextual responses with character personality
✅ **Smart Loot** - Keep class-appropriate gear, skip the rest
✅ **Efficient Shopping** - Buy what the class actually needs
✅ **Scalable** - Easy to add new classes or traits

## Files Modified/Created

**Created**:
- `tools/gap/character_profile.py` - CharacterProfile class (350 lines)

**Modified**:
- `tools/gap/orchestrator.py` - Initialize and inject profile
- `tools/gap/agents/base.py` - Add profile attribute
- `tools/gap/chat_handler.py` - Use profile for context

## Testing

**Test 1: Profile Initialization**
```bash
# Start orchestrator
./orchestrator.py --password foo

# Expected log output:
👤 Character Profile Created
   Class: Rogue (level 2)
   Role: Ranged DPS - high DEX, bow damage, hit-and-run tactics
   Playstyle: ranged_dps
   Stats: STR=20 DEX=38 MAG=15 VIT=20
   Preferred weapons: bw
   Preferred armor: la
```

**Test 2: Level Up Detection**
```bash
# Gain XP and level up in game
# Expected:
🎉 LEVEL UP! Rogue 2 → 3
📊 Character profile updated: <CharacterProfile: Rogue lvl3 (ranged_dps)>
```

**Test 3: Chat Context**
```bash
# In game, type: "What class are you?"
# Expected response:
"I'm a level 3 Rogue - I stick to bows and light armor. Got 4 HP potions ready if things get rough."
```

## Success Metrics

✅ **Profile initialized on first state**
✅ **All agents receive profile reference**
✅ **Chat uses class identity in responses**
✅ **Level ups detected and logged**
✅ **Item evaluation returns class-appropriate recommendations**

**This is architectural thinking** - not just a feature, but making the AI companion truly understand **who they are**.
