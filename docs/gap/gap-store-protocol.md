# GAP Headless Store Protocol

## Design Philosophy
- **Human players**: Use UI (unchanged)
- **AI companions**: Use GAP commands (headless API)
- **Same outcomes**: Both can buy/sell/repair, just different interfaces
- **Zero UI changes**: Store UI remains human-only

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Game Store Logic                         │
│  (SmithItems[], HealerItems[], WitchItems[], etc.)         │
└─────────────┬──────────────────────────┬────────────────────┘
              │                          │
     ┌────────▼─────────┐       ┌────────▼──────────┐
     │   Store UI Path  │       │  GAP Headless API │
     │  (for MyPlayer)  │       │ (for companions)  │
     │                  │       │                   │
     │ - StartStore()   │       │ - gap::GetStore() │
     │ - StoreUp/Down() │       │ - gap::BuyItem()  │
     │ - Confirm()      │       │ - gap::SellItem() │
     └──────────────────┘       └───────────────────┘
          (GUI)                    (Commands)
```

## DSL State Extension

### When Companion in Town Near NPC
```
# Current (already working):
NPC=sm@25,45,3;hl@18,50,1

# Enhanced with store inventory:
ST_sm=sw/m/450/12,ax/n/120/8,sh/n/80/5,hp/n/50/1
       ↑  ↑  ↑   ↑
       │  │  │   └─ item_id (for BUY command)
       │  │  └───── price
       │  └──────── quality (n=normal, m=magic, u=unique)
       └─────────── type (sw=sword, ax=axe, hp=potion, etc.)

ST_hl=hp/n/50/1,mp/n/50/2,rj/n/150/3
ST_wt=sc/m/200/1,st/m/300/2
```

### Companion Inventory Summary
```
INV=sw/m/1500,ax/n/200,hp/n/0  # What companion can sell
GOLD=2500                       # How much gold companion has
```

## GAP Commands

### BUY Command
```
BUY sm 12    # Buy item_id 12 from Smith
BUY hl 1     # Buy item_id 1 from Healer
```

**Backend Flow:**
1. Validate companion near NPC (distance <= 2)
2. Check companion has gold
3. Check companion inventory space
4. Execute purchase (same logic as UI confirm)
5. Deduct gold, add item to companion inventory

### SELL Command
```
SELL 5       # Sell inventory slot 5
```

**Backend Flow:**
1. Validate companion in town
2. Get item from slot, check if sellable
3. Calculate sell price (same formula as UI)
4. Remove item, add gold to companion

### REPAIR Command
```
REP 3        # Repair equipped item slot 3
```

**Backend Flow:**
1. Validate companion near Smith
2. Check item durability < max
3. Check companion has gold for repair cost
4. Execute repair (same logic as UI)

### IDENTIFY Command
```
ID 7         # Identify inventory slot 7 at Cain's
```

## Implementation Files

### New Files to Create

#### `Source/gap/gap_stores.h`
```cpp
namespace devilution::gap {

struct StoreItem {
    int item_id;        // Global item index for BUY command
    int price;
    ItemType type;
    std::string type_code;  // For DSL
    char quality;       // 'n', 'm', 'u'
};

// Get store inventory for DSL encoding
std::vector<StoreItem> GetStoreInventory(_talker_id npc_type);

// Headless store operations (companion-only)
bool CompanionBuyItem(Player& companion, _talker_id npc, int item_id);
bool CompanionSellItem(Player& companion, int inv_slot);
bool CompanionRepairItem(Player& companion, int inv_slot);
bool CompanionIdentifyItem(Player& companion, int inv_slot);

} // namespace gap
```

#### `Source/gap/gap_stores.cpp`
```cpp
// Implementation of headless store API
// Reuses existing store arrays but bypasses UI entirely
```

### Modifications to Existing Files

#### `Source/gap/gap_dsl.cpp`
Add store inventory encoding (only when in town):
```cpp
if (leveltype == DTYPE_TOWN) {
    // Existing NPC encoding...

    // NEW: Add store inventories if companion near NPCs
    for (auto npc_type : {TOWN_SMITH, TOWN_HEALER, TOWN_WITCH}) {
        Towner* t = GetTowner(npc_type);
        if (t && player->position.tile.WalkingDistance(t->position) <= 2) {
            auto items = gap::GetStoreInventory(npc_type);
            // Encode as ST_{code}=...
        }
    }
}
```

#### `Source/gap/gap_intent.cpp`
Add command parsing:
```cpp
} else if (cmd == "BUY") {
    // BUY npc_code item_id
    std::string npc_code;
    iss >> npc_code >> intent.param_id;
    intent.action = "buy";
    intent.param_kind = npc_code;  // "sm", "hl", "wt"

} else if (cmd == "SELL") {
    // SELL slot
    intent.action = "sell";
    iss >> intent.param_slot;

} else if (cmd == "REP") {
    // REP slot
    intent.action = "repair";
    iss >> intent.param_slot;

} else if (cmd == "ID") {
    // ID slot
    intent.action = "identify";
    iss >> intent.param_slot;
}
```

Add execution handlers:
```cpp
case "buy":
    success = ExecuteBuy(intent.param_kind, intent.param_id);
    break;
case "sell":
    success = ExecuteSell(intent.param_slot);
    break;
// etc.
```

#### `Source/player.cpp`
Remove ACTION_TALK restriction for companions:
```cpp
case ACTION_TALK:
    #ifdef ENABLE_GAP
    // Allow companions to trigger talk (for quest dialogs)
    // But store interactions go through GAP headless API
    if (&player == MyPlayer || gap::IsCompanion(player.getId())) {
    #else
    if (&player == MyPlayer) {
    #endif
        HelpFlag = false;
        TalkToTowner(player, player.destParam1);
    }
    break;
```

## Python Agent Side

### Enhanced DSL Parser
```python
def parse_dsl_state(dsl_line):
    # ... existing parsing ...

    # Parse store inventories
    stores = {}
    for match in re.finditer(r'ST_(\w+)=([\w/,]+)', dsl_line):
        npc_code = match.group(1)
        items = []
        for item_str in match.group(2).split(','):
            type, qual, price, item_id = item_str.split('/')
            items.append({
                'type': type, 'quality': qual,
                'price': int(price), 'id': int(item_id)
            })
        stores[npc_code] = items

    state['stores'] = stores
    return state
```

### Shopping Agent
```python
class ShoppingAgent(BaseAgent):
    """Manages buying potions, selling junk, repairs"""

    def should_activate(self, state):
        return state.get('in_town') and len(state.get('stores', {})) > 0

    def evaluate(self, state):
        # Check if we need potions
        belt = state.get('belt', [])
        empty_slots = sum(1 for s in belt if s == 'em')

        if empty_slots > 4:
            # Buy health potions from healer
            healer_inv = state['stores'].get('hl', [])
            hp_potions = [i for i in healer_inv if i['type'] == 'hp']

            if hp_potions and state['gold'] >= hp_potions[0]['price']:
                item = hp_potions[0]
                return AgentResponse(
                    command=f"BUY hl {item['id']}",
                    weight=0.7,
                    reasoning=f"Shopping: Buy health potion ({item['price']}g)"
                )

        # Check if we should sell junk items
        # ... selling logic ...

        return None
```

## Benefits

1. **Zero UI Impact**: Human player experience unchanged
2. **Clean Separation**: UI code untouched, GAP API is isolated
3. **First-Class Shopping**: Companion can buy/sell just like humans
4. **LLM-Friendly**: Store data in DSL, decisions via commands
5. **Testable**: Can test store API without rendering UI

## Effort Estimate

- **gap_stores.h/.cpp**: ~150 lines (headless API)
- **gap_dsl.cpp mods**: ~50 lines (store encoding)
- **gap_intent.cpp mods**: ~100 lines (command parsing)
- **player.cpp mod**: ~5 lines (remove talk restriction)
- **Python agent**: ~80 lines (shopping agent)

**Total**: ~400 lines, 4-6 hours work

## Example Scenario

```
# Companion at 24% HP, near Pepin the Healer
ME=25,45,24,80
NPC=hl@26,45,1
ST_hl=hp/n/50/101,mp/n/50/102,rj/n/150/103
GOLD=2500

# Agent decides: need healing potions!
# Python agent sends:
→ BUY hl 101

# C++ backend:
# - Validates companion near Pepin (distance=1)
# - Checks gold (2500 >= 50) ✓
# - Checks inventory space ✓
# - Adds potion to companion belt
# - Deducts 50 gold
# - No UI opens for MyPlayer!

# Next state update:
ME=25,45,24,80
B=hp,hp,hp,em,em,em,em,em  ← New potion!
GOLD=2450
```

## Open Questions

1. Should companions auto-sell trash items when inventory full?
2. Should companions auto-repair damaged equipment?
3. Should companions negotiate better prices (Cha stat)?
4. Should we add a SHOP agent to TownAgent or make it separate?
