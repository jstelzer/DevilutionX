# GAP Polish Changes - Spell Casting & Town Behavior

## Changes Summary (Nov 2, 2025)

### ✅ Spell Casting Implemented

**C++ Engine Changes:**
1. **`Source/gap/gap_dsl.cpp`** (lines 163-208):
   - Enhanced belt encoding to differentiate scroll types
   - New codes: `sh`=heal scroll, `sp`=portal, `sr`=resurrect, `sl`=lightning, `sf`=fireball, `si`=identify
   - Replaces generic `sc` with specific scroll types

2. **`Source/gap/gap_intent.cpp`** (lines 184-188):
   - Simplified `CS` command: `CS slot` (e.g., `CS 2` to use belt slot 2)
   - Removed complex spell+target syntax

3. **`Source/gap/gap_intent.cpp`** (lines 466-515):
   - Implemented `ExecuteCast()` for scroll usage
   - Validates scroll type before casting
   - Uses `UseInvItem()` for proper scroll consumption

**Python Agent Changes:**
1. **`tools/gap/dsl_agent.py`** (lines 28-46):
   - Updated system prompt to include `CS` command
   - Added scroll usage examples

2. **`tools/gap/dsl_parser.py`** (lines 142-147):
   - Documented new scroll codes in parser

3. **`tools/gap/agents/healing.py`** (lines 58-136):
   - Enhanced to use healing scrolls (`sh`) as backup when potions unavailable
   - Priority: potions > scrolls (save scrolls for emergencies)
   - Supports both `US` (use potion) and `CS` (cast scroll) commands

### ✅ Town/Shopping Coordination Fixed

**Issue**: Town agent kept moving to healer but never triggered shopping

**Root Cause**: Town agent (weight 0.7) competed with Shopping agent, preventing purchases

**Fix** (`tools/gap/agents/town.py`, lines 43-66):
- Town agent now defers to Shopping agent when stores are visible
- Returns `NONE` command with weight 0.0 when near vendor with store inventory
- Shopping agent can now execute `BUY` commands without competition

**Additional** (`tools/gap/agents/shopping.py`, lines 91-95):
- Added debug logging for purchase attempts
- Logs: price, gold, belt status for troubleshooting

## Testing Instructions

### Build:
```bash
cd /home/mental/projects/DevilutionX
cmake --build build
```

### Run Game:
```bash
./build/devilutionx --companion-save multi_1.sv --companion-slot 1
```

### Run Agent:
```bash
cd tools/gap
./dev.sh run yourpassword
```

### Test Scenarios:

1. **Healing Scrolls**:
   - Put healing scrolls in belt
   - Take damage
   - Companion should use `CS` command when HP < 35%

2. **Shopping**:
   - Clear belt of HP potions
   - Go to town
   - Companion should:
     - Navigate to Pepin (healer)
     - Stop when near (dist <= 2)
     - Execute `BUY hl <id>` command
   - Check logs for `"Shopping: Recommending BUY"` messages

3. **Scroll Priority**:
   - Remove all HP potions, keep only healing scroll
   - Take damage to 30% HP
   - Companion should use scroll (CS command)

## Expected Log Output

**Scroll Usage:**
```
GAP: Using scroll Scroll of Healing (spell=2) from belt slot 3
GAP: Successfully used scroll from slot 3
Healing: URGENT HP (32%) using heal_scroll at slot 3
```

**Shopping Coordination:**
```
Town: Going to Pepin for potions (0/8, dist=15)
Town: Near Pepin (dist=1) - waiting for stores to populate
Shopping: Recommending BUY hl 1 (price=50, gold=825, belt_hp=0)
📤 Command: BUY hl 1 (took 0.26s)
GAP Store: Companion Rodney buying Potion of Healing for 50 gold
```

## What's Not Implemented (Future)

1. **Cain Interaction** (identify items)
2. **Griswold Interaction** (sell items)
3. **Portal Scrolls** (auto-return to town when inventory full)
4. **Resurrect Scrolls** (save for emergencies)

## Known Issues

- Shopping may fail silently if inventory full
- Need to add inventory space checking before purchases
- Store inventory parsing might not include all item types

## Files Modified

```
Source/gap/gap_dsl.cpp          # Belt scroll encoding
Source/gap/gap_intent.cpp       # CS command + ExecuteCast
tools/gap/dsl_agent.py          # System prompt
tools/gap/dsl_parser.py         # Scroll documentation
tools/gap/agents/healing.py     # Scroll usage logic
tools/gap/agents/town.py        # Shopping coordination
tools/gap/agents/shopping.py    # Debug logging
```
