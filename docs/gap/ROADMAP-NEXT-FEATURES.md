# GAP Next Features Roadmap

**Date**: November 2, 2025
**Status**: Planning for next implementation phase

## Feature 1: Bidirectional Chat Agent (In Progress)

### Current State
- **ChatHandler**: Reactive only, responds to player messages
- **Location**: Separate thread, not part of agent council
- **Context**: Limited game state awareness (HP%, MP%, location)
- **Memory**: None - can't remember previous conversations

### Target State
- **ChatAgent**: Full peer in 10-agent council
- **Bidirectional**: Both reactive (answers) and proactive (initiates)
- **State Aware**: Knows inventory, equipped gear, stats, goals
- **Memory Backed**: Uses SQLite for conversation history and quick lookups

### Use Cases

**Reactive (Player → Companion)**:
```
Player: "What weapon are you using?"
Companion: "I'm wielding a Magic Long Sword +2. Does 18-25 damage."

Player: "Do you have any healing potions?"
Companion: "Yeah, I've got 4 HP potions in my belt and 2 more in my pack."

Player: "What level are you?"
Companion: "Level 5 Rogue. 2,847 XP until level 6."

Player: "What are you doing?"
Companion: "Following you through the catacombs. Killed 12 skeletons so far on this floor."
```

**Proactive (Companion → Player)**:
```
Situation: Belt empty, HP < 50%
Companion: "Running low on healing potions - can you drop me some?"

Situation: Inventory 80%+ full
Companion: "Inventory's getting full, should head back to town soon."

Situation: Found magic bow, companion is warrior
Companion: "Found a magic bow but I'm a warrior - want it?"

Situation: Near death experience
Companion: "That was close! Down to 15% HP."

Situation: Level up
Companion: "Level up! I'm now level 6. Got 5 stat points to spend."

Situation: Stuck on unreachable loot
Companion: "Can't reach that item, moving on."
```

### Architecture

**Option A: Replace ChatHandler with ChatAgent**
```python
class ChatAgent(BaseAgent):
    """Handles both reactive and proactive communication"""

    def __init__(self, **kwargs):
        super().__init__(name="Chat", **kwargs)
        self.message_queue = queue.Queue()  # Player messages
        self.last_proactive_message = 0  # Cooldown tracking

    def should_activate(self, state):
        # Activate if:
        # 1. Player sent a message
        # 2. Something worth mentioning (proactive)
        return (not self.message_queue.empty() or
                self._has_proactive_message(state))

    def _evaluate_impl(self, state):
        # Handle player message if present
        if not self.message_queue.empty():
            return self._handle_player_message(state)

        # Otherwise check for proactive communication
        return self._generate_proactive_message(state)
```

**Option B: Keep ChatHandler + Add ChatAgent**
- ChatHandler: Async reactive responses (fast templates)
- ChatAgent: Proactive communication only
- Pro: Don't break existing chat
- Con: Two systems doing similar things

**Recommendation**: Option A (unified ChatAgent)

### SQLite Schema for Quick Lookups

**Table: companion_state** (updated every tick)
```sql
CREATE TABLE companion_state (
    id INTEGER PRIMARY KEY,
    tick INTEGER,

    -- Equipment (for "What weapon are you using?")
    weapon_left TEXT,      -- "Magic Long Sword +2"
    weapon_right TEXT,     -- "Tower Shield"
    armor TEXT,            -- "Full Plate Mail"
    helm TEXT,             -- "Magic Helm of Protection"

    -- Inventory counts (for "Do you have potions?")
    hp_potions INTEGER,
    mp_potions INTEGER,
    scrolls INTEGER,
    gold INTEGER,

    -- Stats (for "What level are you?")
    level INTEGER,
    experience INTEGER,
    stat_points INTEGER,

    -- Location (for "Where are you?")
    floor INTEGER,
    in_town INTEGER,
    position_x INTEGER,
    position_y INTEGER,

    -- Session stats (for "How many monsters killed?")
    kills_this_floor INTEGER,
    items_picked_up INTEGER,
    gold_spent INTEGER,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Table: chat_history**
```sql
CREATE TABLE chat_history (
    id INTEGER PRIMARY KEY,
    tick INTEGER,
    sender TEXT,           -- "player" or "companion"
    message TEXT,
    response TEXT,         -- Companion's response (if sender=player)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Implementation Plan

**Phase 1: State Serialization** (~1 hour)
- Update orchestrator to write `companion_state` every tick
- Only update when values change (efficiency)
- Parse equipped gear names from DSL

**Phase 2: ChatAgent Reactive** (~2 hours)
- Convert ChatHandler to ChatAgent
- Query SQLite for instant answers
- LLM gets full context from database

**Phase 3: ChatAgent Proactive** (~1 hour)
- Detect situations worth mentioning
- Cooldown system (don't spam)
- Priority levels (urgent vs. FYI)

**Phase 4: Memory Integration** (~1 hour)
- Store conversation history
- LLM can reference past conversations
- "Remember when I asked about potions?"

### Proactive Message Triggers

**Urgent (weight 0.8)**:
- HP < 20% and no potions
- Surrounded by 5+ enemies
- Inventory full and trying to pick up unique item

**Important (weight 0.5)**:
- HP potions < 2
- Inventory > 80% full
- Level up
- Found inappropriate loot for class

**FYI (weight 0.2)**:
- Killed boss/unique monster
- Reached new floor
- Near death recovery (HP was <10%, now >50%)

**Cooldown**: 30 seconds between proactive messages (don't spam)

### Example LLM Prompts

**Reactive** (player asks question):
```python
prompt = f"""You're a {profile.class_name} adventurer (level {level}).

Current equipment:
- Weapon: {weapon_left}
- Armor: {armor}

Inventory:
- {hp_potions} HP potions
- {mp_potions} MP potions
- {gold} gold

Player asks: "{player_message}"

Answer naturally and concisely (1-2 sentences). Be helpful but casual."""
```

**Proactive** (companion initiates):
```python
prompt = f"""You're a {profile.class_name} in the dungeon with your friend.

Situation: You have {hp_potions} HP potions (need 4), HP is at {hp_pct}%.

Express this need naturally without being demanding. Keep it short (1 sentence).

Examples:
- "Running low on healing potions, only got 1 left."
- "Could use some health pots if you've got extras."
"""
```

### Success Metrics

✅ **Reactive**: Answers questions about inventory/gear/stats instantly
✅ **Proactive**: Expresses needs without being annoying
✅ **Context Aware**: Knows full game state via SQLite
✅ **Memory**: References past conversations
✅ **Natural**: Feels like talking to a real party member

---

## Feature 2: Stat-Based Gear Comparison

### Current State
- **Quality Only**: Normal → Magic → Unique
- **No Stats**: Can't see damage, AC, requirements
- **Blind Upgrades**: Buys magic item even if worse stats

### Target State
- **Full Stats**: Knows damage ranges, AC values, stat requirements
- **Smart Comparison**: Compares actual combat effectiveness
- **Value Analysis**: Price vs. benefit (don't overpay for 5% upgrade)

### Use Cases

**Scenario 1: Weapon Upgrade**
```
Equipped: Normal Long Sword (10-15 damage)
Shop: Magic Short Sword (8-12 damage, 500g)
Decision: SKIP (lower damage despite magic quality)

Shop: Magic Bastard Sword (18-25 damage, 800g)
Decision: BUY (60% damage increase, worth the gold)
```

**Scenario 2: Armor Upgrade**
```
Equipped: Normal Full Plate (AC 25)
Shop: Magic Chain Mail (AC 18, 600g)
Decision: SKIP (worse AC despite magic quality)

Shop: Magic Full Plate +5 (AC 30, 1200g)
Decision: BUY (20% better AC)
```

**Scenario 3: Stat Requirements**
```
Shop: Unique Great Axe (30-45 damage, requires 80 STR)
Character: Rogue with 25 STR
Decision: SKIP (can't equip - insufficient STR)
```

### C++ Implementation

**Extend DSL Equipment Encoding**:

Current: `EQ=hl:sw_m,hr:sh,ch:la`
New: `EQ=hl:sw_m:18-25:50S:30D,hr:sh:8AC,ch:la_m:22AC:40S`

Format: `slot:type_qual:damage/AC:reqSTR:reqDEX:reqMAG`

**Example**:
```
hl:sw_m:18-25:50S:30D = Hand Left: Magic Sword, 18-25 damage, requires 50 STR 30 DEX
hr:sh:8AC = Hand Right: Normal Shield, 8 AC
ch:la_m:22AC:40S = Chest: Magic Light Armor, 22 AC, requires 40 STR
```

**Code Changes** (`Source/gap/gap_dsl.cpp`):
```cpp
// Add item stats to encoding
equipped << slot_codes[slot] << ":" << type_code;

// Add damage/AC
if (eq_item._itype == ItemType::Sword || ...) {
    equipped << ":" << eq_item._iMinDam << "-" << eq_item._iMaxDam;
} else if (eq_item._itype == ItemType::LightArmor || ...) {
    equipped << ":" << eq_item._iAC << "AC";
}

// Add requirements
if (eq_item._iMinStr > 0) equipped << ":" << eq_item._iMinStr << "S";
if (eq_item._iMinDex > 0) equipped << ":" << eq_item._iMinDex << "D";
if (eq_item._iMinMag > 0) equipped << ":" << eq_item._iMinMag << "M";
```

### Python Implementation

**Add to Character Profile**:
```python
def compare_weapons(self, current, candidate):
    """Compare two weapons, return upgrade score"""

    # Can we even equip it?
    if not self._can_equip(candidate):
        return {"upgrade": False, "reason": "Insufficient stats"}

    # Compare average damage
    current_avg = (current.min_dam + current.max_dam) / 2
    candidate_avg = (candidate.min_dam + candidate.max_dam) / 2

    damage_increase = (candidate_avg - current_avg) / current_avg

    # 20%+ damage = strong upgrade
    if damage_increase > 0.20:
        return {"upgrade": True, "score": 0.9, "reason": f"+{damage_increase*100:.0f}% damage"}
    elif damage_increase > 0.10:
        return {"upgrade": True, "score": 0.7, "reason": f"+{damage_increase*100:.0f}% damage"}
    elif damage_increase > 0:
        return {"upgrade": True, "score": 0.5, "reason": f"+{damage_increase*100:.0f}% damage"}
    else:
        return {"upgrade": False, "reason": "No improvement"}
```

**Update Shopping Agent**:
```python
# Instead of quality comparison
if equipped_item["quality"] == "normal" and item_quality == "magic":
    should_buy = True

# Use stat comparison
comparison = self.profile.compare_weapons(equipped_weapon, shop_weapon)
if comparison["upgrade"] and comparison["score"] > 0.6:
    should_buy = True
    logger.info(f"Shopping: {comparison['reason']}")
```

### Store Encoding

**Extend Store Inventory DSL**:

Current: `ST_sm=sw/m/500/1,ax/n/200/2`
New: `ST_sm=sw/m/500/1:18-25:50S,ax/n/200/2:12-18:40S`

### Implementation Estimate

**C++ Changes**: ~100 lines
- Encode equipped item stats
- Encode store item stats
- Add to `gap_dsl.cpp`

**Python Changes**: ~150 lines
- Parse item stats in `dsl_parser.py`
- Add comparison logic to `character_profile.py`
- Update `shopping.py` to use stat comparison
- Update `griswold.py` to consider stats when selling

**Total**: ~4 hours work

### Success Metrics

✅ **Smart Buying**: Only buys items that are actual upgrades
✅ **Stat Aware**: Knows damage/AC values
✅ **Requirements**: Doesn't buy items it can't equip
✅ **Value Based**: Weighs cost vs. benefit
✅ **Class Appropriate**: Warriors prioritize damage, rogues prioritize DEX

---

## Priority

1. **ChatAgent** (Start Now)
   - More immediate player-facing benefit
   - Makes companion feel alive
   - Easier to implement

2. **Stat Comparison** (After Chat)
   - More technical
   - Requires C++ work
   - Polish on top of working system

---

## Timeline Estimate

**ChatAgent**: 5-6 hours
- Phase 1: State serialization (1h)
- Phase 2: Reactive chat (2h)
- Phase 3: Proactive messages (1h)
- Phase 4: Memory integration (1h)

**Stat Comparison**: 4-5 hours
- C++ encoding (2h)
- Python parsing (1h)
- Comparison logic (1h)
- Integration testing (1h)

**Total**: ~10 hours for both features

Both would represent massive upgrades to the companion's intelligence and personality!
