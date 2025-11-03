# GAP Companion Damage Bug - Root Cause Analysis

## Problem

**User Report**: "Is the agent being awarded exp? She's still lvl 1, while I am 5. Is she actually dealing damage? I see her shoot but haven't see a kill shot."

## Investigation Summary

The companion AI is **NOT dealing damage** to monsters. This is why she's stuck at level 1 - she can't kill monsters, so she never gets XP.

## Root Cause

### The Bug (player.cpp:621-635)

```cpp
bool PlrHitMonst(Player &player, Monster &monster, bool adjacentDamage = false)
{
    // ... damage calculation (lines 522-620) ...

    int dam = RandomIntBetween(mind, maxd);
    // ... damage modifiers ...

    if (&player == MyPlayer) {  // ❌ BUG: Only local player applies damage!
        ApplyMonsterDamage(DamageType::Physical, monster, dam);
    }

    // ... life steal, knockback, etc. ...
}
```

**The restriction**: `if (&player == MyPlayer)` means ONLY the human-controlled local player can apply damage. The companion's attacks calculate damage but **never actually apply it**.

### How Damage and XP Attribution Works

1. **Attack Processing** (`msg.cpp:3369-3370`)
   - `CMD_ATTACKID` → `OnAttackMonster(message, player)`
   - Sets `player.destAction = ACTION_ATTACKMON`

2. **Attack Execution** (`player.cpp:798`)
   - When animation reaches attack frame: `PlrHitMonst(player, *monster)`
   - Calculates damage based on player stats, weapon, modifiers

3. **Damage Application** (`player.cpp:634`)
   - **ONLY if** `&player == MyPlayer`: `ApplyMonsterDamage(DamageType::Physical, monster, dam)`
   - Companion's damage is calculated but **discarded**

4. **Monster Death** (`player.cpp:685`)
   - When `(monster.hitPoints >> 6) <= 0`: `M_StartKill(monster, player)`
   - Calls `monster.tag(player)` to set `whoHit |= 1 << player.getId()`
   - Since companion never reduces HP, monster never dies from companion attacks

5. **XP Attribution** (`player.cpp:2455-2465`)
   - `AddPlrMonstExper(lvl, exp, monster.whoHit)` distributes XP to tagged players
   - Companion never tags monsters (because they never kill them)
   - Companion gets 0 XP

## Evidence

### GAP Intent Processing Works Correctly

```cpp
// gap_intent.cpp:377 - ExecuteAttack sends proper command
NetSendCmdParam1ForPlayer(controlled_id, true, CMD_ATTACKID, monsterId);
```

### Command Routing Works Correctly

```cpp
// msg.cpp:3369 - Command routes to companion player object
case CMD_ATTACKID:
    return HandleCmd(OnAttackMonster, player, pCmd, maxCmdSize);
```

### Damage Calculation Works for Companion

The companion's attack goes through the full damage calculation (lines 522-620), including:
- Hit chance calculation
- Weapon damage
- Stat bonuses
- Monster resistances
- Critical hits

**But the damage is thrown away at line 621.**

## Impact

- ✅ Companion can navigate
- ✅ Companion can attack (animation plays)
- ✅ Companion's attacks calculate damage correctly
- ❌ **Damage is never applied to monsters**
- ❌ Monsters never die from companion attacks
- ❌ Companion never gets XP
- ❌ Companion stuck at level 1 forever
- ❌ Companion is essentially cosmetic in combat

## Design Principle Violation

From `CLAUDE.md`:

> **FUNDAMENTAL RULE**: AI companions must be indistinguishable from real players to the game engine. Never create special case logic - instead, ensure companions follow the same initialization and systems as human players.

The `if (&player == MyPlayer)` check violates this principle. In real multiplayer:
- Player 2's attacks apply damage
- Player 3's attacks apply damage
- All players can kill monsters and get XP

The companion should work the same way - **remove the restriction, don't add special cases**.

## The Fix

### Option 1: Remove MyPlayer Restriction (RECOMMENDED)

```cpp
bool PlrHitMonst(Player &player, Monster &monster, bool adjacentDamage = false)
{
    // ... damage calculation ...

    // ✅ FIXED: Apply damage for ANY player (multiplayer-like)
    ApplyMonsterDamage(DamageType::Physical, monster, dam);

    // ... rest of function ...
}
```

**Benefits**:
- Companion works like real multiplayer player
- No special cases
- Future-proof for multiple companions
- Follows design principles

**Risks**:
- May need to verify delta functions handle non-MyPlayer correctly
- Network sync might need adjustment

### Option 2: Special Case for GAP (NOT RECOMMENDED)

```cpp
#ifdef ENABLE_GAP
    if (&player == MyPlayer || gap::IsCompanion(player)) {
        ApplyMonsterDamage(DamageType::Physical, monster, dam);
    }
#else
    if (&player == MyPlayer) {
        ApplyMonsterDamage(DamageType::Physical, monster, dam);
    }
#endif
```

**Problems**:
- Violates design principle
- Adds complexity
- Doesn't scale to multiple companions
- Wrong architectural approach

## Similar Issues Fixed Previously

From `CLAUDE.md`:

> **✅ Success Story: Universal Damage System (Sept 2025)**
> **Problem**: Companions made hit sounds but took no damage due to engine restricting damage to `MyPlayerId` only.
>
> **Correct Solution**: Remove player ID restriction entirely - ALL players take damage from monster attacks

This is the **exact same pattern**:
- Previously: Only `MyPlayerId` could **receive** damage
- Now: Only `MyPlayer` can **deal** damage

Both need the same fix: **remove the restriction**.

## Recommended Action

1. **Remove** the `if (&player == MyPlayer)` restriction in `player.cpp:621`
2. **Test** that companion can kill monsters and gain XP
3. **Verify** network sync works correctly in multiplayer
4. **Update** gap-agent-capabilities.md to reflect companion can now level up

## Code Location

- **Bug**: `/home/mental/projects/DevilutionX/Source/player.cpp:621-635`
- **Function**: `bool PlrHitMonst(Player &player, Monster &monster, bool adjacentDamage)`
- **Line to remove**: `if (&player == MyPlayer) {`
- **Line to keep**: `ApplyMonsterDamage(DamageType::Physical, monster, dam);`

## Expected Behavior After Fix

1. Companion attacks monster
2. Damage is calculated (already works)
3. Damage is applied (currently broken, will be fixed)
4. Monster HP decreases
5. When monster dies, `M_StartKill(monster, companion)` is called
6. Monster is tagged with companion's player ID
7. `AddPlrMonstExper()` distributes XP to companion
8. Companion levels up normally
9. Full autonomy achieved! 🎉
