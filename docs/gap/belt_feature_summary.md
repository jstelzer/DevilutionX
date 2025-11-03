# Phase 2a: Belt/Inventory Integration - COMPLETE ✅

## Changes Made

### C++ Side (gap_dsl.cpp)
- Added belt data to DSL state output: `B=type,type,type,...` (8 slots)
- Belt item types:
  - `hp` = healing potion (IMISC_HEAL, IMISC_FULLHEAL)
  - `mp` = mana potion (IMISC_MANA, IMISC_FULLMANA)
  - `rj` = rejuvenation potion (IMISC_REJUV, IMISC_FULLREJUV)
  - `sc` = scroll (IMISC_SCROLL, IMISC_SCROLLT)
  - `ms` = misc item
  - `em` = empty slot

**Example DSL output:**
```
T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1 L=71@35,19,10 B=hp,mp,em,em,hp,hp,rj,em
```

### Python Side (dsl_parser.py)
- Added `state["belt"]` array to parsed state
- Parses `B=` field into list of 8 item types
- Example: `["hp", "mp", "em", "em", "hp", "hp", "rj", "em"]`

### HealingAgent (agents/healing.py)
**Old behavior:**
- Always tried to use slot 0: `USE 0`
- No awareness of actual belt contents

**New behavior:**
- Scans belt for available healing items
- Smart potion selection:
  - HP < 20% (CRITICAL): Prefers rejuv > healing
  - HP 20-50%: Prefers healing > rejuv (save rejuvs)
  - HP 50-90%: Uses any available
- Returns `NONE` if no healing items available (prevents wasted commands)
- Logs which slot and potion type used

**Example logs:**
```
🎯 Decision: Healing → USE 1 (score: 8.00, weight: 0.80)
   Reasoning: Healing: URGENT HP (30%) using heal at slot 1

🎯 Decision: Healing → USE 6 (score: 10.00, weight: 1.00)
   Reasoning: Healing: CRITICAL HP (18%) using rejuv at slot 6

🎯 Decision: Combat → AT 27 (score: 6.40, weight: 0.80)
   Alternatives: [('Healing', 0.00), ...]
   Reasoning: Healing: URGENT HP (30%) but NO POTIONS
```

### Orchestrator (orchestrator.py)
- Added belt display to periodic state logs
- Example: `belt=[hp,mp,em,em,hp,hp,rj,em]`

## Testing

### Python Unit Test (Verified ✅)
```bash
python3 -c "
import sys; sys.path.insert(0, 'tools/gap')
from agents.healing import HealingAgent

agent = HealingAgent(model='test')
test_state = {
    'me': (50, 50, 30, 100),  # 30% HP
    'belt': ['em', 'hp', 'mp', 'rj', 'em', 'em', 'em', 'em']
}
response = agent.evaluate(test_state)
print(f'{response.command}: {response.reasoning}')
# Output: USE 1: Healing: URGENT HP (30%) using heal at slot 1
"
```

### Live Game Testing
```bash
# Terminal 1: Start game
cd build
./devilutionx --companion-save multi_1.sv --companion-slot 1

# Terminal 2: Run orchestrator
cd tools/gap
./orchestrator.py --model qwen2.5:3b --debug

# Watch for:
# - Belt contents in state logs: belt=[hp,mp,em,...]
# - Healing decisions using correct slots: USE 1, USE 6, etc.
# - NO POTIONS warnings when belt empty
```

## Benefits

1. **No Wasted Commands**: Agent won't try to use empty belt slots
2. **Smart Resource Management**: Saves rejuvs for critical situations
3. **Better Survival**: Uses optimal potion for current HP level
4. **Clear Debug Info**: Logs show exactly which slot/potion used
5. **Foundation for Loot Agent**: Belt data enables inventory-aware item pickup

## Next Steps (Phase 2b)

- Add item quality/type to LOOT entries
- Create LootAgent to evaluate items before pickup
- Prevent picking up junk when belt/inventory full

