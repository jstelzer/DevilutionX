# DevilutionX GAP Project

GAP (Game Agent Protocol) enables LLM control of Diablo characters via IPC/JSON protocol.

## Project Overview
- **Goal**: Run an LLM on NVIDIA GPU to play Diablo autonomously/cooperatively
- **Architecture**: Unix socket IPC, JSON protocol, compile flag `-DENABLE_GAP`
- **Integration**: Hooks in `game_loop()` for state, `GameEventHandler()` for input
- **Status**: Multiplayer companion mode with chat fully functional

## Notes

* When generating scripts/python note I'm on linux so only use \n not \r\n for line ending.s

## Completed Features Summary

**Phase 1-3.5 Complete**: Basic protocol, combat, LLM integration, level transitions all working.

### Key Achievements:
- ✅ **GAP Protocol**: Unix socket IPC with JSON messaging
- ✅ **State Extraction**: Player, monsters, items, vision system  
- ✅ **Combat System**: Attack, movement, tactical behaviors
- ✅ **LLM Integration**: Ollama bridge via MCP server
- ✅ **Level Transitions**: Automatic companion following through stairs/portals
- ✅ **Chat System**: Bidirectional conversation with AI companion
- ✅ **Multiplayer Mode**: Companion loads from save files

### Current Usage:
```bash
# Start game with companion
./devilutionx --companion-save multi_1.sv --companion-slot 1

# Start AI agent
python3 tools/gap/mcp_server.py --companion-slot 1 --model qwen2.5:3b --password "foo"
```

**Recommended Models**: qwen2.5:3b (fast), llama3.2:latest (balanced), llama3.1:8b (powerful)

## Active Development Focus

### Priority Features:
1. **Combat Improvements**: Defensive behavior, threat prioritization
2. **Survival Systems**: Auto-healing, emergency retreating  
3. **Loot Intelligence**: Item evaluation, inventory management
4. **Formation Keeping**: Stay near player, tactical positioning

## GAP Protocol Data Structure (Current)

### Enhanced State Message Example:
```json
{
  "type": "state",
  "tick": 12345,
  "data": {
    "player": {
      "hp": 150, "hp_max": 200,
      "mana": 80, "mana_max": 120,
      "pos": [50, 45], "level": 8,
      "in_town": false
    },
    "vision": {
      "light_radius": 10,
      "player_pos": [50, 45],
      "walkable_grid": [[true, false, true, ...], ...]
    },
    "monsters": [
      {
        "id": 42, "name": "Skeleton",
        "pos": [52, 47], "distance": 3,
        "hp": 45, "hp_max": 60, "hp_percent": 75,
        "armor": 12, "is_alive": true, "is_minion": false
      }
    ],
    "items": [
      {
        "id": 15, "name": "Health Potion", "type": "potion",
        "pos": [51, 46]
      },
      {
        "id": 16, "name": "Gold", "type": "gold",
        "pos": [53, 48], "value": 250
      }
    ]
  }
}
```

This gives LLMs complete tactical context: spatial awareness, enemy intel, loot opportunities, and movement constraints - exactly what's needed for intelligent decision-making!

## Key Implementation Details
- **Socket**: `/tmp/devilutionx-gap.sock`
- **Build**: `-DENABLE_GAP=ON` compile flag
- **Pathfinding**: `MakePlrPath()` + `NetSendCmdLoc()`
- **Player ID**: `MyPlayerId >= MAX_PLRS` (unsigned)

### MCP Agent Architecture:
```
┌─────────────┐    GAP Socket    ┌─────────────┐    HTTP API    ┌─────────────┐
│   Diablo    │◄────────────────►│ MCP Server  │◄──────────────►│   Ollama    │
│   (GAP)     │   JSON Messages  │ (Bridge)    │  Natural Lang  │  (LLM GPU)  │
└─────────────┘                  └─────────────┘                └─────────────┘
                                        │
                                        ▼
                                 ┌─────────────┐
                                 │   Claude    │
                                 │ Code (MCP)  │
                                 └─────────────┘
```

**Key Components:**
- **MCP Server**: Bridges GAP socket ↔ Ollama API  
- **State Translator**: Game state → Natural language context
- **Intent Parser**: LLM decisions → GAP intents
- **Context Manager**: Maintain game session memory
- **Prompt Templates**: Personality system & tactical guidance

**Implementation Location**: `tools/gap/` directory for MCP server, prompts, and LLM integration tooling.

### Testing & Known Issues
- **Test agents**: See `tools/gap/` directory
- **Known limitations**: Complex pathfinding struggles, spell casting not implemented
- **Performance**: Varies by LLM model (qwen2.5:3b recommended)

## Architectural Approaches

### Companion Mode (Current Implementation) ✅
- **Concept**: Load saved character into multiplayer slot
- **Status**: Working with chat, level transitions functional
- **Issue**: Movement intent execution bug in MCP server

### Headless Peer Mode (Future)
- **Concept**: Two separate game instances via TCP/IP
- **Benefits**: Natural multiplayer, independent saves
- **Status**: Planning phase

### Current Known Issues
- **Movement Bug**: MCP server movement intents fail (combat agent works)
- **Investigation**: JSON format identical, suspected socket timing issue

## Recent Protocol Enhancements

### Phase 0 Complete ✅ 
- **Intent Types**: `cast`, `pickup`, `use_potion`, `interact`, `path`, `explore`
- **State Additions**: Belt info, spells, objects, exploration data
- **Chat System**: Bidirectional LLM-powered conversation
- **Safety Systems**: Python survival reflexes, emergency healing
- **Navigation**: A* pathfinding with stuck detection

### Chat Commands:
- `!ai help` - Show commands
- `!ai status` - Display state  
- `!ai debug` - Debug info

## Recent Updates

### Enhanced Combat & AI Integration (Dec 2024) ✅
- **Wired Navigation & Survival Systems**: Integrated `navigation.py` and `survival_reflexes.py` into `mcp_server.py`
- **Combat Priority System**: Added smart target prioritization (low HP + close distance = high priority)
- **Enhanced Combat Prompts**: Crystal clear attack guidance with threat levels ("ATTACK_NOW", "ATTACK", "IGNORE")
- **Survival Override**: Emergency healing (<25% HP) and kiting (4+ enemies) override LLM decisions
- **A* Pathfinding**: NavigationPlanner enhances LLM movement with robust obstacle avoidance
- **Python Environment**: Fixed `setup.sh` and `pyproject.toml` for proper uv/venv compatibility

### Chat Separation (Sept 2025)
- Separated chat messages from state payloads
- Reduced JSON size by ~30%
- Instant chat responses without state bundling

## Development Environment

### Quick Setup:
```bash
cd tools/gap
./setup.sh              # Auto-setup with uv or traditional venv
./dev.sh run mypassword  # Run enhanced MCP server  
./dev.sh test           # Validate all systems
```

### Development Commands:
- `./dev.sh run [password]` - Run enhanced MCP server
- `./dev.sh combat [password]` - Run combat agent
- `./dev.sh test` - Run validation tests
- `./dev.sh format` - Format code with black
- `./dev.sh lint` - Check code with ruff
- `./dev.sh clean` - Clean logs and cache

### Enhanced AI Features:
- ⚔️ **Aggressive Combat**: AI prioritizes combat over exploration
- 🎯 **Smart Targeting**: Low HP enemies first, threat-based prioritization  
- 🚨 **Survival Reflexes**: Emergency healing and kiting override LLM
- 🧭 **A* Navigation**: Robust pathfinding with waypoint chunking
- 💬 **Natural Chat**: Bidirectional conversation with context awareness

## Combat Debug Investigation (Dec 2024)

### Issue: Companion Not Attacking or Taking Damage
**Observed**: Companion visible to enemies (they attack), but companion doesn't perceive threats or attack back.

### Root Cause Analysis ✅
**AI Systems Working Correctly:**
- ✅ Monster detection and prioritization system functional
- ✅ Survival reflexes and combat prompts working  
- ✅ Target prioritization: low HP + close distance = high priority
- ✅ Enhanced debug logging shows complete AI decision chain

**Game-Side Issue Identified:**
- ❌ **Companion receives 0 monsters from game**: `🩺 SURVIVAL CHECK: HP 70/70 (0 monsters nearby)`
- ❌ **No raw monster data**: Game sends empty monster arrays to companion
- ❌ **LLM never gets combat instructions**: `📍 SENDING TO LLM: No monsters, exploration mode`

### Debug Evidence
```
2025-09-04 15:45:17,702 - DEBUG - 👥 COMPANION FILTER: pos_changed=False, close_monsters=0, chat=False, other_players=True
2025-09-04 15:45:17,702 - DEBUG - 🩺 SURVIVAL CHECK: HP 70/70 (0 monsters nearby)  
2025-09-04 15:45:17,702 - DEBUG - No monsters detected in current area
2025-09-04 15:45:17,702 - DEBUG - 📍 SENDING TO LLM: No monsters, exploration mode
```

### Potential Game-Side Causes
1. **Companion Player ID Issue**: Companion slot might not receive monster visibility data
2. **GAP Protocol Filtering**: Game filtering out monsters for companion characters  
3. **Vision System Bug**: Companion vision radius might be 0 or broken
4. **Level/Area Mismatch**: Companion not in same area as visible monsters

### Enhanced Debug Tools Added ✅
- 🗂️ **Raw monster data logging**: Shows what game sends before AI processing
- 🎯 **Monster prioritization logs**: Combat target selection with threat levels
- ⚔️ **LLM instruction logs**: What combat data reaches the AI
- 🚨 **Survival override logs**: Emergency healing/kiting triggers
- 👥 **Companion filter logs**: State processing decisions

### Next Investigation Steps
- Check GAP source code for companion monster visibility implementation
- Verify companion player ID gets same vision data as main player
- Test if companion and main player are in same dungeon level/area
- Look for GAP protocol errors in game console during monster encounters

### Status
**AI combat system is fully functional** - issue is in game-side monster data delivery to companion characters.

## Technical Debt
- Replace custom JSON with nlohmann/json
- Add GAP config file  
- Implement state delta compression
- ~~Fix MCP server movement bug~~ ✅ Fixed with navigation integration
- **Investigate GAP companion monster visibility** ❌ Game-side issue

