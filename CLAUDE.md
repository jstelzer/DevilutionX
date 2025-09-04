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

### Chat Separation (Sept 2025)
- Separated chat messages from state payloads
- Reduced JSON size by ~30%
- Instant chat responses without state bundling

## Technical Debt
- Replace custom JSON with nlohmann/json
- Add GAP config file
- Implement state delta compression
- Fix MCP server movement bug

