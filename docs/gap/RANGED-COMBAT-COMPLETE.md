# Ranged Combat Enhancement - COMPLETE ✅

**Date**: Nov 2025
**Status**: Ready for Testing

## Problem Statement

User reported: *"the rogue... I gave her a bow to use again. She still face tanks. In fact, in rooms with archers, it would be great if she focused on the archers, let me cleanup melee and eventually help her with ranged."*

## Solution Implemented

Enhanced the Combat agent with **class-aware tactical prompts** that provide different combat guidance based on character class and equipped weapons.

### Changes Made

#### 1. Character Profile Methods (character_profile.py)

**Added `get_combat_style()` method** (lines 231-251):
```python
def get_combat_style(self) -> str:
    """Return 'ranged', 'melee', or 'caster' based on class and stats"""
    if self.is_ranged:
        return "ranged"
    elif self.is_caster:
        return "caster"
    elif self.is_melee:
        return "melee"
    else:
        # Fallback: analyze stats
        if self.magic > max(self.strength, self.dexterity):
            return "caster"
        elif self.dexterity > self.strength:
            return "ranged"
        else:
            return "melee"
```

**Enhanced `get_combat_context()` method** (lines 253-268):
- Ranged: "RANGED ATTACKER - High DEX bow user, hit-and-run tactics, kite enemies, prioritize archers"
- Caster: "SPELLCASTER - High MAG spell damage, manage mana, keep distance from threats"
- Warrior: "MELEE TANK - High VIT, absorb damage, protect allies, rush threats"
- Barbarian: "MELEE BERSERKER - High damage output, aggressive tactics, finish low HP enemies"

#### 2. Combat Agent Enhancements (combat.py)

**Class Detection** (lines 53-68):
- Primary: Use `self.profile.get_combat_style()` and `self.profile.get_combat_context()`
- Fallback: Detect from equipped weapon (`bw` = bow) or class stats

**Enemy Analysis** (lines 75-97):
- Count archer vs melee enemies in room
- Flag enemies as BOSS, ARCHER, or MELEE
- Include distance and HP% for tactical decisions

**Ranged Combat Tactics** (lines 100-115):
```
RANGED TACTICS (BOW USER):
- PRIORITIZE ARCHERS FIRST (let player handle melee)
- Keep distance 6+ tiles from melee enemies (kite!)
- Attack from max range
- If surrounded, target closest threat then retreat

PRIORITY:
1. ARCHERS at medium range (4-8 tiles) - Your specialty!
2. Low HP enemies (finish them off)
3. Enemies charging at you (self-defense)

Current situation: {ranged_count} archers, {melee_count} melee
```

**Caster Tactics** (lines 117-129):
```
CASTER TACTICS (MAGE):
- Keep distance 5+ tiles
- Prioritize dangerous/boss enemies
- Manage mana (MP={mp_pct}%)

PRIORITY:
1. BOSS/unique monsters (most dangerous)
2. ARCHERS (range threats)
3. Close enemies (defensive)
```

**Melee Tactics** (lines 131-143):
```
MELEE TACTICS (WARRIOR):
- Rush close enemies
- Tank damage (HP={hp_pct}%)
- Prioritize immediate threats

PRIORITY:
1. Low HP enemies (finish them)
2. Closest threats (dist < 3)
3. Boss/unique monsters
```

## Expected Behavior Changes

### Before (Generic Combat):
- All classes used same "attack closest enemy" logic
- No awareness of combat role or enemy types
- Rogue with bow would run into melee range

### After (Class-Aware Combat):

**Rogue with Bow**:
- ✅ Prioritizes ARCHERS first (user's request!)
- ✅ Maintains 6+ tile distance from melee enemies
- ✅ Uses hit-and-run tactics
- ✅ Lets player handle melee mobs

**Warrior**:
- ✅ Rushes into melee range
- ✅ Tanks damage for party
- ✅ Prioritizes close threats

**Sorcerer**:
- ✅ Keeps distance (5+ tiles)
- ✅ Targets boss/unique enemies first
- ✅ Manages mana resources

## Testing Checklist

- [ ] Start game with rogue companion wielding bow
- [ ] Enter combat room with mixed archer + melee enemies
- [ ] Verify companion targets archers FIRST
- [ ] Verify companion maintains distance from melee
- [ ] Check combat logs show ranged tactics prompt
- [ ] Confirm kiting behavior (retreat when surrounded)

## Integration Status

- ✅ Character profile methods added
- ✅ Combat agent enhanced
- ✅ No orchestrator changes needed (combat already integrated)
- ✅ Backward compatible (falls back gracefully if no profile)
- ✅ Works for all classes (warrior, rogue, sorcerer)

## Files Modified

1. `tools/gap/character_profile.py` - Added combat style methods
2. `tools/gap/agents/combat.py` - Enhanced with class-aware tactics

## Performance Notes

- **LLM Token Impact**: ~50-80 additional tokens per combat decision (minimal)
- **Response Time**: No change (same number of LLM calls)
- **Accuracy**: Expected improvement in target selection for ranged characters

## Next Steps

1. **Test with rogue + bow** - Verify archer prioritization works
2. **Monitor combat logs** - Check if LLM follows ranged tactics
3. **Tune weights** - Adjust if combat decisions still too passive
4. **Add distance awareness** - If needed, add explicit "TOO CLOSE, RETREAT!" signals

## User Feedback Required

*"Try the rogue with bow now and see if she focuses archers and keeps distance!"*
