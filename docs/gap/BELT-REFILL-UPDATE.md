# Belt Refill Priority System - Update

**Date**: November 2, 2025
**Status**: Complete ✅

## Problem Identified

Companion died at 19% HP despite having 10+ HP potions in inventory.

**Root Cause**: Belt was empty → couldn't use potions in combat → Movement/Combat agents (weight 0.4-0.6) beat Inventory agent (weight 0.4) → companion fought with empty belt → death.

## Solution Implemented

Added **urgency-based priority system** to Inventory agent that dynamically adjusts weights based on danger level.

### New Priority Hierarchy

**HP Potions (Health)**:
1. **EMERGENCY** (HP<30% + empty belt + has potions): **Weight 0.95**
   - Beats almost everything (healing with potions = 1.0)
   - Immediately refills belt when in danger

2. **PROACTIVE** (empty belt + has potions): **Weight 0.7**
   - Beats movement (0.5-0.6) and combat (0.6-0.8)
   - Refills belt BEFORE getting into dangerous situations

3. **NORMAL** (belt_hp < 4): **Weight 0.4**
   - Original behavior - top up belt when running low
   - Lower than combat but still important

**MP Potions (Casters)**:
1. **EMERGENCY** (MP<20% + empty belt + has potions): **Weight 0.85**
2. **PROACTIVE** (empty belt + has potions): **Weight 0.65**
3. **NORMAL** (belt_mp < 2): **Weight 0.4**

**Healing Scrolls (Last Resort)**:
1. **URGENT** (HP<40% + empty belt + no potions + has scrolls): **Weight 0.8**
2. **NORMAL** (backup scrolls): **Weight 0.3**

### Fallback: Out of Options

If truly out of healing (HP<30% + no potions anywhere):

1. **Healing Agent Retreat** (weight 0.9): Move to player position
2. **Chat Warning** (weight 0.8): Alert player about critical situation
3. **Survive**: Try to stay alive for player TP

## Decision Flow

```
HP drops to 19%, belt empty, 10 potions in inventory:

  1. InventoryAgent: EMERGENCY belt refill (weight 0.95)
     → "BELT 1 0" - move HP potion to belt slot 0
     ✅ WINS - highest priority

  vs.

  2. HealingAgent: Critical healing (weight 1.0)
     ❌ BLOCKED - no belt potions available

  3. CombatAgent: Attack monster (weight 0.6-0.8)
     ❌ LOSES - lower priority than emergency refill

  4. MovementAgent: Follow player (weight 0.5-0.6)
     ❌ LOSES - lower priority than emergency refill

Result: Belt refilled → potions usable → survival!
```

## Code Changes

**Modified**: `tools/gap/agents/inventory.py`

- Added urgency detection: `is_emergency`, `is_proactive`
- Dynamic weight calculation based on HP%, belt status, inventory
- Enhanced logging: 🚨 for emergencies, ⚠️ for proactive
- Applied to HP potions, MP potions, and healing scrolls

**Lines Added**: ~40 lines of urgency logic

## Testing

```bash
export PYTHONPATH=/home/mental/projects/DevilutionX/tools/gap:$PYTHONPATH
python3 -c "from agents.inventory import InventoryAgent; print('✅ OK')"
# ✅ OK
```

## Expected Behavior

**Scenario 1: Emergency (HP=19%, belt empty, has 10 potions)**
```
🚨 Inventory: EMERGENCY belt refill - low HP + empty belt: hp → belt slot 0
📤 Command: BELT 1 0 (took 0.00s)
```

**Scenario 2: Proactive (HP=100%, belt empty, has 8 potions, entering dungeon)**
```
⚠️ Inventory: Proactive belt refill - empty belt: hp → belt slot 0
📤 Command: BELT 1 0 (took 0.00s)
```

**Scenario 3: Out of Options (HP=19%, no potions anywhere)**
```
🚨 Healing: RETREAT to player - CRITICAL HP (19%) NO POTIONS
💬 Chat: CRITICAL! I'm at 19% HP and completely out of healing potions! Need to get to town ASAP!
📤 Command: MV 79 38 (took 0.00s)
```

## Benefits

✅ **Prevents Deaths**: Refills belt before running out of options
✅ **Smart Priorities**: Emergency situations override combat/movement
✅ **Proactive Management**: Refills belt during safe moments, not just emergencies
✅ **Clear Logging**: Visual indicators (🚨/⚠️) show urgency level
✅ **Class-Aware**: Warriors prioritize HP, casters balance HP+MP

## Integration with Chat Agent

Chat warnings (Phase 3) complement inventory management:

- **Inventory priority 0.95**: Try to refill first
- **Chat warning 0.8**: Alert player if refill impossible
- **Healing retreat 0.9**: Move to safety while player prepares TP

This creates a layered safety system where the companion tries to solve the problem (refill belt), communicates if it can't (chat warning), and retreats as last resort (healing agent).

## Files Modified

**Modified**:
- `tools/gap/agents/inventory.py` (+40 lines)

**Total**: ~40 lines
