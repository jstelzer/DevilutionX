# Phase 2b: Item Quality/Type & LootAgent - COMPLETE ✅

## Changes Made

### C++ Side (gap_dsl.cpp:84-143)

Enhanced LOOT encoding with item metadata:

**Old format:** `L=id@x,y,value;...`
**New format:** `L=id@x,y,value,type,qual;...`

**Type codes:**
- `go` = gold
- `sw` = sword, `ax` = axe, `bw` = bow, `mc` = mace, `st` = staff
- `sh` = shield
- `la/ma/ha` = light/medium/heavy armor, `hl` = helm
- `rg` = ring, `am` = amulet
- `ms` = misc (potions, scrolls, etc.)

**Quality codes:**
- `n` = normal
- `m` = magic (blue)
- `u` = unique (gold)

**Example DSL output:**
```
L=71@35,19,150,sw,m;83@37,18,500,go,n
```
= Magic sword (value 150) at (35,19) + 500 gold at (37,18)

### Python Side (dsl_parser.py:100-134)

- Added `type` and `quality` fields to loot items
- Backward compatible (defaults to `ms`/`n` if missing)
- Example parsed item:
  ```python
  {
      "id": 71,
      "x": 35, "y": 19,
      "value": 150,
      "type": "sw",
      "quality": "m",
      "dist": 5
  }
  ```

### LootAgent (agents/loot.py) ✨ NEW

Smart item pickup specialist with scoring algorithm:

**Dormancy:**
- Deactivates during heavy combat (3+ monsters)
- Only evaluates when items present

**Scoring factors:**
1. **Quality multiplier:**
   - Unique: 3.0x
   - Magic: 2.0x
   - Normal: 1.0x

2. **Type score:**
   - Gold: 1.0 (always good)
   - Weapons: 0.8
   - Armor: 0.7
   - Jewelry: 0.9 (usually valuable)
   - Misc: 0.3 (unless magic/unique)

3. **Distance multiplier:**
   - ≤2 tiles: 1.2x
   - 3-5 tiles: 1.0x
   - 6-10 tiles: 0.8x
   - >10 tiles: 0.5x

4. **Special rules:**
   - Gold ≥50: minimum 0.5 score (always pick up)
   - Unique items: minimum 0.9 score
   - Low HP (<50%): boost potion priority to 0.9
   - Full belt: reduce potion priority by 50%

**Example behavior:**
```python
# Unique sword vs gold → picks unique
Loot: u/sw value=200 dist=2 → PK 71 (weight=1.00)

# Gold is always valuable
Loot: n/go value=500 dist=1 → PK 83 (weight=1.00)

# Skips junk misc items
Loot: n/ms value=10 dist=5 → NONE (no valuable items)

# Dormant during combat
4 monsters nearby → agent not activated
```

### Orchestrator (orchestrator.py:18, 58, 128-167)

**Priority hierarchy updated:**
1. HEALING: 10/8 (critical survival)
2. COMBAT: 8/6 (high priority)
3. **LOOT: 4 (NEW - medium priority)**
4. MOVEMENT: 3 (fallback)

**Example decision logs:**
```
🎯 Decision: Loot → PK 71 (score: 3.60, weight: 0.90)
   Alternatives: [('Movement', 0.90)]
   Reasoning: Loot: u/sw value=200 dist=2

🎯 Decision: Combat → AT 27 (score: 6.40, weight: 0.80)
   Alternatives: [('Loot', 2.00), ('Movement', 0.90)]
   Reasoning: Combat: AT 27
```

## Testing

### Python Unit Tests (Verified ✅)
```bash
python3 -c "
import sys; sys.path.insert(0, 'tools/gap')
from agents.loot import LootAgent

agent = LootAgent(model='test')

# Test 1: Gold
test_state = {
    'me': (50, 50, 80, 100),
    'belt': ['hp', 'mp', 'em', 'em', 'em', 'em', 'em', 'em'],
    'mobs': [],
    'loot': [
        {'id': 83, 'x': 51, 'y': 50, 'value': 500, 'type': 'go', 'quality': 'n', 'dist': 1}
    ]
}
response = agent.evaluate(test_state)
print(f'{response.command}: {response.reasoning}')
# Output: PK 83: Loot: n/go value=500 dist=1
"
```

**Test results:**
- ✅ Gold (500g): PK 83 (weight=1.00)
- ✅ Unique sword vs gold: PK 71 (weight=1.00) - prioritizes unique!
- ✅ Junk misc item: NONE (weight=0.00) - correctly skips
- ✅ During combat (4 monsters): dormant (correct!)

### Build Status
```
[100%] Built target devilutionx ✅
```

### Live Game Testing

```bash
# Terminal 1: Start game
cd build && ./devilutionx --companion-save multi_1.sv --companion-slot 1

# Terminal 2: Run orchestrator with loot agent
cd tools/gap && ./orchestrator.py --model qwen2.5:3b --debug

# Watch for:
# - Item metadata in state: L=71@35,19,150,sw,m
# - Loot decisions: PK 71 (unique sword)
# - Combat priority: attacks before looting
# - Gold pickup: always grabs gold
```

## Benefits

1. **Intelligent Pickup**: Knows difference between unique sword and normal junk
2. **Combat Focus**: Won't loot during heavy fighting (3+ monsters)
3. **Resource Awareness**: Considers belt space for potions
4. **Distance Smart**: Prioritizes nearby valuable items
5. **Quality Recognition**: Unique/magic items get priority
6. **Gold Greed**: Always picks up significant gold piles

## Example Decision Flow

**Scenario: Unique sword, gold, and 2 monsters nearby**

1. HealingAgent: HP=80% → NONE (no healing needed)
2. CombatAgent: 2 monsters → AT 27 (weight=0.8, score=6.4)
3. LootAgent: Unique sword → PK 71 (weight=0.9, score=3.6)
4. MovementAgent: Follow player → MV 75 68 (weight=0.3, score=0.9)

**Winner:** Combat (score 6.4) → AT 27

After combat ends (0 monsters):
1. LootAgent: Unique sword → PK 71 (weight=1.0, score=4.0)
2. MovementAgent: Follow player → MV 75 68 (weight=0.3, score=0.9)

**Winner:** Loot (score 4.0) → PK 71

Then:
1. LootAgent: Gold → PK 83 (weight=1.0, score=4.0)
**Winner:** Loot → PK 83

## Next Steps (Phase 2c)

- Wire stats/attributes into state protocol
- Create StatsAgent for level-up allocation
- Add spell info for SpellAgent (future)

