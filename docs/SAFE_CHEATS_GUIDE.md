# Safe Way to Cheat in DevilutionX - Using Built-in Lua Console

## ⚠️ WARNING: External Save Editors Can Corrupt Saves!
As you discovered, directly modifying save files can easily corrupt them. DevilutionX save format is complex with checksums and specific structures. **Use the built-in Lua console instead!**

## Enabling Debug Mode & Lua Console

### Step 1: Build DevilutionX in Debug Mode
```bash
cd /home/mental/projects/DevilutionX
cmake -S. -Bbuild-debug -DCMAKE_BUILD_TYPE=Debug
cmake --build build-debug -j$(nproc)
```

### Step 2: Run Debug Build
```bash
./build-debug/devilutionx
```

### Step 3: Open Lua Console In-Game
Press **`** (backtick/grave key) or **~** (tilde) to open the Lua console

## Available Lua Commands

### Player Stats Commands

#### Level Up
```lua
-- Level up once
dev.player.stats.levelUp()

-- Level up multiple times (e.g., to max level 50)
dev.player.stats.levelUp(49)  -- If you're level 1, this gets you to 50
```

#### Max Out Stats
```lua
-- Set all attributes (STR, MAG, DEX, VIT) to maximum
dev.player.stats.setAttrToMax()
```

#### Fix Equipment Stat Requirements (Common Issue)
If you leveled up but still can't equip items that require certain stats:

```lua
-- Check your current stats (base vs effective)
dev.player.stats.checkStats()  -- Shows all current values

-- The issue: Base stats were changed but effective stats weren't recalculated
-- Solution: Force stat recalculation
dev.player.stats.recalculate()

-- Alternative: If above doesn't exist, try manual stat refresh
dev.player.stats.refresh()
```

**Why this happens:** The game tracks both "base stats" (your raw character attributes) and "effective stats" (base + equipment bonuses + spell effects). Equipment requirements check effective stats, so if you only changed base stats without recalculating, the equipment checker still sees old values.

#### Health & Mana
```lua
-- Refill health and mana to full
dev.player.stats.rejuvenate()

-- Adjust health (positive or negative)
dev.player.stats.adjustHealth(100)  -- Add 100 HP
dev.player.stats.adjustHealth(-50)  -- Remove 50 HP

-- Adjust mana
dev.player.stats.adjustMana(100)  -- Add 100 mana
```

### Gold Commands
```lua
-- Give maximum gold (9,999,999)
dev.player.gold.give()

-- Give specific amount
dev.player.gold.give(50000)

-- Remove gold
dev.player.gold.take(1000)
```

### Items Commands
```lua
-- Spawn items (check available item functions)
dev.items.spawn("The Grandfather")  -- Best sword
dev.items.spawn("Windforce")        -- Best bow
dev.items.spawn("Royal Circlet")    -- Best helm
dev.items.spawn("Stormshield")      -- Best shield
```

### Level/Dungeon Commands
```lua
-- Warp to different dungeon levels
dev.level.warp(1)   -- Cathedral level 1
dev.level.warp(5)   -- Catacombs level 1
dev.level.warp(9)   -- Caves level 1
dev.level.warp(13)  -- Hell level 1
dev.level.warp(16)  -- Diablo's lair
```

## Debug Mode Features (If Compiled with _DEBUG)

When running a debug build, you also get:
- **God Mode**: Take no damage
- **Invisibility**: Monsters ignore you
- **Debug Vision**: See entire level
- **Debug Grid**: Show tile information

## Complete Max Character Script

Run these commands in sequence in the Lua console:

```lua
-- Max level
dev.player.stats.levelUp(49)

-- Max stats
dev.player.stats.setAttrToMax()

-- Full health/mana
dev.player.stats.rejuvenate()

-- Max gold
dev.player.gold.give()

-- Optional: Give yourself some good items
-- (Item spawning syntax may vary)
```

## Checking Available Commands

In the Lua console, you can explore available commands:

```lua
-- See what's available
dev
dev.player
dev.player.stats
dev.player.gold
dev.items
dev.level
```

Use Tab for autocomplete suggestions!

## Troubleshooting

### Console Not Opening?
- Make sure you built with Debug mode (`CMAKE_BUILD_TYPE=Debug`)
- Try different keys: ` ~ or sometimes F1

### Commands Not Working?
- Some commands may only work in certain game states
- Make sure you're in-game, not in menus
- Check exact syntax - Lua is case-sensitive

### Can't Equip Items After Leveling Up?
This is a common issue where base stats were changed but effective stats weren't recalculated:

```lua
-- First, check what the game thinks your stats are
dev.player.stats.checkStats()

-- If effective stats are lower than base stats, force recalculation
dev.player.stats.recalculate()
-- or try:
dev.player.stats.refresh()
```

If the above functions don't exist, try exploring what's actually available:
```lua
-- See what functions are really available
dev.player.stats
-- Then use Tab for autocomplete to see actual function names
```

### Want to Revert Changes?
- Unfortunately, there's no built-in undo
- Always backup saves before using cheats:
  ```bash
  cp ~/.local/share/diasurgical/devilution/*.sv ~/devilution_backup/
  ```

## Why This Is Better Than Save Editing

1. **Safe**: Uses game's own functions, won't corrupt saves
2. **Immediate**: See results instantly
3. **Flexible**: Can adjust values precisely
4. **Reversible**: Can reduce stats/gold if needed
5. **No File Format Knowledge Required**: Don't need to understand save structure

## Additional Resources

- Check `Source/lua/modules/dev/` for all available cheat modules
- Read `Source/panels/console.cpp` for console implementation
- Look at `Source/lua/modules/dev/player/` for player-specific cheats

## Final Note

The save file format includes:
- Complex item seed generation
- Checksum validation
- Packed bit fields
- Variable-length structures

This is why direct save editing often fails - one wrong byte can invalidate the entire save. Always use the built-in Lua console for modifications!