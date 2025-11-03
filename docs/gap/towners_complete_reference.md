# Complete Towner Reference

## All 13 Towners in Diablo

Successfully implemented full detection and parsing for all NPCs in Tristram town.

## Towner Type Mapping

| ID | Enum | Type Code | Name | Role | Shop Items |
|----|------|-----------|------|------|------------|
| 0 | TOWN_SMITH | `sm` | Griswold the Blacksmith | Sells weapons, armor, repairs | ⚔️ Swords, axes, armor |
| 1 | TOWN_HEALER | `hl` | Pepin the Healer | Sells potions, healing | 🧪 HP/Mana/Rejuv potions |
| 2 | TOWN_DEADGUY | `dg` | Wounded Townsman | Quest NPC (Butcher quest) | ❌ No shop |
| 3 | TOWN_TAVERN | `tv` | Ogden the Tavern owner | Sign of the Hanging Man | 🍺 Quest info |
| 4 | TOWN_STORY | `cn` | Cain the Elder | Identifies items, lore | 🔍 Identify items |
| 5 | TOWN_DRUNK | `dr` | Farnham the Drunk | Rumors, quest info | 🍻 Quest hints |
| 6 | TOWN_WITCH | `wt` | Adria the Witch | Sells magic items, staves | 🔮 Mana potions, staves, books |
| 7 | TOWN_BMAID | `bm` | Gillian the Barmaid | Healing, quest info | ❤️ Free healing |
| 8 | TOWN_PEGBOY | `pg` | Wirt the Peg-legged boy | Sells premium items | 💰 Expensive rare items |
| 9 | TOWN_COW | `cw` | Cow | Easter egg | 🐄 Moo |
| 10 | TOWN_FARMER | `fm` | Lester the farmer | Quest NPC (Cow quest) | 🌾 Quest items |
| 11 | TOWN_GIRL | `gl` | Celia | Quest NPC (Gharbad) | 👧 Quest info |
| 12 | TOWN_COWFARM | `cf` | Complete Nut | Quest NPC (Cow quest) | 🥜 Quest completion |

## DSL Format

**In town, NPCs are encoded as:**
```
NPC=type@x,y,id;type@x,y,id;...
```

**Example:**
```
NPC=sm@62,62,0;hl@23,21,1;wt@80,62,6;tv@55,58,3;cn@70,52,4
```

## Python State Format

```python
state["npcs"] = [
    {"type": "sm", "name": "Griswold", "x": 62, "y": 62, "id": 0, "dist": 24},
    {"type": "hl", "name": "Pepin", "x": 23, "y": 21, "id": 1, "dist": 56},
    {"type": "wt", "name": "Adria", "x": 80, "y": 62, "id": 6, "dist": 42},
    ...
]
```

## Shopping Priority (TownAgent)

### Current Implementation

**Priority 1: Health Potions (All Classes)**
- NPC: Pepin the Healer (`hl`)
- Trigger: `hp_potions < 3`
- Action: Navigate to Pepin → `IN {pepin_id}`

**Priority 2: Mana Potions (Sorcerers)**
- NPC: Adria the Witch (`wt`)
- Trigger: `class == 2 and mp_potions < 2`
- Action: Navigate to Adria → `IN {adria_id}`

### Future Enhancements

**Griswold (Smith) - Equipment & Repair**
- Buy better weapons/armor when gold available
- Repair damaged equipment (detect durability)
- Sell junk items

**Cain (Elder) - Identify**
- Interact to identify unidentified items in inventory
- Free identification service (vs paying Adria)

**Wirt (Pegboy) - Premium Items**
- Browse expensive/rare items
- Only visit if lots of gold available

**Gillian (Barmaid) - Free Healing**
- Visit when HP < 100% to heal for free
- Alternative to using potions

## Quest NPCs (Informational Only)

These NPCs don't have shops but provide quest information:

- **Wounded Townsman** (`dg`) - Butcher quest trigger
- **Farnham** (`dr`) - Drunk who gives quest hints
- **Ogden** (`tv`) - Tavern owner, quest info
- **Lester** (`fm`) - Farmer, cow quest
- **Celia** (`gl`) - Girl, Gharbad quest
- **Complete Nut** (`cf`) - Cow quest completion
- **Cow** (`cw`) - Easter egg (secret cow level)

## Finding NPCs in Code

**Find specific NPC:**
```python
pepin = next((npc for npc in npcs if npc["type"] == "hl"), None)
adria = next((npc for npc in npcs if npc["type"] == "wt"), None)
griswold = next((npc for npc in npcs if npc["type"] == "sm"), None)
cain = next((npc for npc in npcs if npc["type"] == "cn"), None)
```

**Find nearest NPC of type:**
```python
healers = [npc for npc in npcs if npc["type"] == "hl"]
if healers:
    nearest = min(healers, key=lambda n: n["dist"])
```

**Find all shop NPCs:**
```python
shops = [npc for npc in npcs if npc["type"] in ["sm", "hl", "wt", "pg"]]
```

## Interaction Command

**Navigate and interact:**
```python
# Move toward NPC
command = f"MV {npc['x']} {npc['y']}"

# When adjacent (dist <= 1), interact
command = f"IN {npc['id']}"
```

**C++ execution (gap_intent.cpp:484-515):**
```cpp
bool GapIntentProcessor::ExecuteInteract(int object_id) {
    // Finds towner by ID
    // Checks if adjacent (dx <= 1 && dy <= 1)
    // Sends CMD_OPOBJXY to open dialog
    NetSendCmdLocForPlayer(controlled_id, true, CMD_OPOBJXY, objPos);
}
```

## Testing

**Verify all towners are detected:**
```bash
cd tools/gap
python3 -c "
import sys; sys.path.insert(0, '.')
from dsl_parser import parse_dsl_state

test_dsl = 'T=1 F=0 ME=50,50,100,100 TN=1 NPC=sm@62,62,0;hl@23,21,1;dg@45,40,2;tv@55,58,3;cn@70,52,4;dr@60,45,5;wt@80,62,6;bm@56,59,7;pg@35,28,8;cw@30,65,9;fm@25,70,10;gl@40,55,11;cf@32,68,12'

state = parse_dsl_state(test_dsl)
print(f'Found {len(state[\"npcs\"])} towners')
for npc in state['npcs']:
    print(f'  {npc[\"name\"]:20s} at ({npc[\"x\"]},{npc[\"y\"]})')
"
```

**Expected output:**
```
Found 13 towners
  Griswold             at (62,62)
  Pepin                at (23,21)
  Wounded Townsman     at (45,40)
  Ogden                at (55,58)
  Cain                 at (70,52)
  Farnham              at (60,45)
  Adria                at (80,62)
  Gillian              at (56,59)
  Wirt                 at (35,28)
  Cow                  at (30,65)
  Lester               at (25,70)
  Celia                at (40,55)
  Complete Nut         at (32,68)
```

## Benefits

**Complete NPC awareness:**
- ✅ All 13 towners detected and tracked
- ✅ Positions and distances calculated
- ✅ Type-based lookup (find healer, smith, etc.)
- ✅ Easy to extend for new behaviors

**Smart shopping:**
- Companion knows where every shop is
- Can navigate to appropriate vendor
- Class-aware (Sorcerers go to Adria for mana)

**Future expansion ready:**
- Add Griswold for equipment/repair
- Add Cain for item identification
- Add Gillian for free healing
- Add Wirt for premium shopping
