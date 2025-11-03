# GAP Agent Mechanics - Implementation Status

## Currently Implemented ✅

### 1. Movement (MV command)
**Status**: ✅ **Fully Working**

**Command**: `MV x y`

**C++ Implementation**: `gap_intent.cpp:278-327`
```cpp
bool GapIntentProcessor::ExecuteMove(int x, int y) {
    MakePlrPath(*player, target, true);
    player->destAction = ACTION_WALK;
    NetSendCmdLocForPlayer(controlled_id, true, CMD_WALKXY, target);
}
```

**What it does**:
- Companion navigates to target position
- Uses game's pathfinding (MakePlrPath)
- Works in both town and dungeon
- **Autonomous**: Yes, no human intervention needed

---

### 2. Attack (AT command)
**Status**: ✅ **Fully Working**

**Command**: `AT monster_id` or `AT x y`

**C++ Implementation**: `gap_intent.cpp:329-418`
```cpp
bool GapIntentProcessor::ExecuteAttack(int x, int y) {
    // Monster ID attack
    if (y == -1) {
        NetSendCmdParam1ForPlayer(controlled_id, true, CMD_ATTACKID, monsterId);
    } else {
        // Position attack
        NetSendCmdLocForPlayer(controlled_id, true, CMD_SATTACKXY, target);
    }
}
```

**What it does**:
- Companion attacks specific monster by ID
- Or attacks a ground position
- Handles both melee and ranged weapons
- **Autonomous**: Yes, fully automatic combat

---

### 3. Pickup (PK command)
**Status**: ✅ **Fully Working**

**Command**: `PK item_id`

**C++ Implementation**: `gap_intent.cpp:436-466`
```cpp
bool GapIntentProcessor::ExecutePickup(int item_id) {
    // Check if item is adjacent (dx <= 1 && dy <= 1)
    NetSendCmdPItem(true, CMD_REQUESTGITEM, itemPos, item);
}
```

**What it does**:
- Companion picks up items from ground
- Must be adjacent to item (dist <= 1)
- Uses same pickup as human player
- **Autonomous**: Yes, fully automatic looting

**Current Agent**: LootAgent evaluates items by quality/type and recommends best pickup

---

### 4. Interact (IN command)
**Status**: ⚠️ **Partially Working** (opens dialog, doesn't auto-buy)

**Command**: `IN object_id` or `IN npc_id`

**C++ Implementation**: `gap_intent.cpp:484-515`
```cpp
bool GapIntentProcessor::ExecuteInteract(int object_id) {
    // Check if object/NPC is adjacent
    NetSendCmdLocForPlayer(controlled_id, true, CMD_OPOBJXY, objPos);
}
```

**What it does**:
- Opens NPC dialog (Pepin, Adria, Griswold, etc.)
- Activates objects (chests, shrines, levers)
- Must be adjacent (dist <= 1)
- **Autonomous**: **Partial** - Opens shop but can't auto-buy

**Current Agent**: TownAgent navigates to NPCs and opens their shop

**Limitation**: Shop dialog opens, but companion can't automatically purchase items. Human player must click "Buy" in the opened UI.

---

### 5. Chat (SAY command)
**Status**: ✅ **Fully Working**

**Command**: `SAY message`

**C++ Implementation**: `gap_intent.cpp:530-584`
```cpp
bool GapIntentProcessor::ExecuteChat(const std::string& message) {
    GAPChatHandler::getInstance().SendAIResponse(message);
}
```

**What it does**:
- Companion sends chat messages to player
- Visible in game chat window
- Supports multi-part messages (breaks at 100 chars)
- **Autonomous**: Yes, companion can communicate freely

**Current Agent**: ChatHandler uses LLM (llama3.1:8b) for natural conversations

---

## Not Yet Implemented ❌

### 6. Use Potion (USE command)
**Status**: ❌ **Stubbed Out**

**Command**: `USE slot`

**C++ Implementation**: `gap_intent.cpp:468-482`
```cpp
bool GapIntentProcessor::ExecuteUsePotion(const std::string& kind, int slot) {
    // TODO: Implement potion usage from belt/inventory
    std::cerr << "GAP: Potion usage not yet implemented" << std::endl;
    return false;  // ❌ Always fails
}
```

**Why it's needed**:
- Companion knows when HP is low (HealingAgent detects < 40% HP)
- Companion knows which belt slot has health potions
- But **can't actually drink them**

**What's missing**:
```cpp
// Need to implement something like:
if (slot >= 0 && slot < MaxBeltItems) {
    Item& potion = player->SpdList[slot];
    if (!potion.isEmpty()) {
        NetSendCmdParam1(true, CMD_USEBELTITEM, slot);  // ← This command might exist
        return true;
    }
}
```

**Impact**: Companion relies on passive regeneration or human player feeding potions

---

### 7. Cast Spell (CS command)
**Status**: ❌ **Stubbed Out**

**Command**: `CS spell_name t=monster_id` or `CS spell_name xy=x,y`

**C++ Implementation**: `gap_intent.cpp:420-434`
```cpp
bool GapIntentProcessor::ExecuteCast(int slot, int x, int y) {
    // TODO: Implement spell casting by slot
    std::cerr << "GAP: Spell casting not yet implemented" << std::endl;
    return false;  // ❌ Always fails
}
```

**Why it's needed**:
- Sorcerers need to cast offensive spells (Fireball, Lightning, etc.)
- All classes can cast utility spells (Town Portal, Healing, etc.)
- Currently, companion can only melee/ranged attack

**What's missing**:
- Map spell names to spell IDs
- Send spell cast command
- Target selection (monster vs ground)

**Impact**: Sorcerer companions are severely handicapped (no spells!)

---

### 8. Buy from Shop
**Status**: ❌ **Not Implemented** (UI-level, not command-level)

**No GAP command exists**

**How shopping currently works**:
1. Companion sends `IN {npc_id}` → Opens shop dialog ✅
2. Human player sees shop UI with items
3. Human player clicks item → Selects it
4. Human player clicks "Buy" → Purchase completes
5. Shop dialog closes

**What's needed for auto-buy**:
```cpp
// Pseudocode - doesn't exist yet
bool GapIntentProcessor::ExecuteBuyItem(int npc_id, int item_index) {
    // 1. Ensure shop is open (ActiveStore == TalkID::HealerBuy)
    // 2. Navigate to item (StoreUp/StoreDown to set CurrentItemIndex)
    // 3. Check if we have enough gold
    // 4. Trigger purchase (StoreEnter() - simulates Enter key)
    return true;
}
```

**Complexity**: This requires UI-level control, not just game commands. The store system is UI-based:
- `stores.h` shows UI functions: `StoreUp()`, `StoreDown()`, `StoreEnter()`
- `ActiveStore` tracks which shop is open
- `CurrentItemIndex` tracks selected item
- `HealerItems[]` contains Pepin's inventory

**Workaround**: Companion navigates to NPC and opens shop, human player completes purchase

**Impact**: Companion can't fully autonomously restock potions

---

### 9. Sell to Shop
**Status**: ❌ **Not Implemented**

**No GAP command exists**

**Similar to buying** - requires UI-level control:
- Switch to "Sell" tab
- Select item from inventory
- Confirm sale

**Impact**: Companion can't sell junk items or manage inventory space

---

### 10. Repair Equipment
**Status**: ❌ **Not Implemented**

**No GAP command exists**

**Similar to buying** - requires:
- Open Griswold's shop (`IN griswold_id`) ✅ Works
- Switch to "Repair" tab
- Select damaged item
- Confirm repair

**Impact**: Companion's equipment degrades and becomes useless

---

### 11. Identify Items
**Status**: ❌ **Not Implemented**

**No GAP command exists**

**Similar to repair** - requires:
- Open Cain's dialog (`IN cain_id`) ✅ Works
- Select unidentified item
- Confirm identification

**Impact**: Companion doesn't know stats of magic/unique items

---

## Summary Table

| Feature | Command | Status | Autonomous? | Notes |
|---------|---------|--------|-------------|-------|
| **Movement** | `MV x y` | ✅ Working | Yes | Full pathfinding |
| **Attack** | `AT id` | ✅ Working | Yes | Melee + ranged |
| **Pickup** | `PK id` | ✅ Working | Yes | Auto-loot items |
| **Interact** | `IN id` | ⚠️ Partial | Partial | Opens dialog only |
| **Chat** | `SAY msg` | ✅ Working | Yes | Natural LLM chat |
| **Use Potion** | `USE slot` | ❌ Stub | No | Not implemented |
| **Cast Spell** | `CS spell` | ❌ Stub | No | Not implemented |
| **Buy Item** | N/A | ❌ Missing | No | UI-level needed |
| **Sell Item** | N/A | ❌ Missing | No | UI-level needed |
| **Repair** | N/A | ❌ Missing | No | UI-level needed |
| **Identify** | N/A | ❌ Missing | No | UI-level needed |

## What Companion Can Do Autonomously

**Full Autonomy:**
- ✅ Navigate town and dungeons
- ✅ Attack monsters (melee/ranged)
- ✅ Pick up valuable loot
- ✅ Chat with player naturally
- ✅ Follow player through levels
- ✅ Make tactical decisions (Combat, Healing, Loot, Movement agents)

**Partial Autonomy (requires human help):**
- ⚠️ Knows when potions needed, navigates to Pepin, opens shop, but human must buy
- ⚠️ Knows equipment needs repair, could navigate to Griswold, but can't repair
- ⚠️ Detects HP low, knows which potion to use, but can't drink it

**Can't Do:**
- ❌ Drink health/mana potions from belt
- ❌ Cast spells (huge limitation for Sorcerers!)
- ❌ Buy items from shops
- ❌ Sell junk items
- ❌ Repair equipment
- ❌ Identify magic items

## Priority Implementations

### High Priority (Basic Survival)

**1. Use Potion** - Critical for autonomous survival
```cpp
// Estimated effort: 2 hours
// Add to gap_intent.cpp:
bool GapIntentProcessor::ExecuteUsePotion(const std::string& kind, int slot) {
    if (slot < 0 || slot >= MaxBeltItems) return false;

    Item& beltItem = player->SpdList[slot];
    if (beltItem.isEmpty()) return false;

    // Trigger belt item usage
    NetSendCmdParam1ForPlayer(controlled_id, true, CMD_USEBELTITEM, slot);
    return true;
}
```

**Impact**: Companion can heal itself during combat!

---

### Medium Priority (Combat Effectiveness)

**2. Cast Spell** - Essential for Sorcerer class
```cpp
// Estimated effort: 4 hours (spell mapping complexity)
// Need to map spell names to IDs and handle targeting
bool GapIntentProcessor::ExecuteCast(SpellID spell, int target_x, int target_y) {
    // Set active spell
    // Cast at target (monster or ground)
    NetSendCmdLocParam1(true, CMD_SPELLXY, {target_x, target_y}, spell);
    return true;
}
```

**Impact**: Sorcerers become viable!

---

### Low Priority (Quality of Life)

**3. Buy/Sell/Repair** - Requires UI integration
```cpp
// Estimated effort: 8-12 hours (complex UI state machine)
// Need to:
// - Track ActiveStore state
// - Navigate store UI (StoreUp/Down)
// - Trigger purchases (StoreEnter)
// - Handle "No Room" / "No Money" states
```

**Impact**: Full autonomy in town

## Current Gameplay Flow

**In Dungeon:**
```
Companion detects monster → Attacks → Loots items → Follows player
HP gets low → ⚠️ CAN'T use potion → Retreats to player → Hopes to survive
```

**In Town:**
```
Companion detects low potions → Navigates to Pepin → Opens shop → ⚠️ Human clicks Buy
Companion sees chat → Responds naturally with LLM → Player feels companionship
```

**Result**: Companion is **70% autonomous** - can fight, loot, navigate, and communicate, but relies on human for survival items and shopping.

## Recommendations

1. **Implement USE potion first** - Biggest impact for least effort
2. **Add spell casting second** - Makes Sorcerers playable
3. **Shopping automation later** - Complex but high polish factor
