# DevilutionX GAP Project

GAP (Game Agent Protocol) enables LLM control of Diablo characters via IPC/JSON protocol.

## Project Overview
- **Goal**: Run an LLM on NVIDIA GPU to play Diablo autonomously/cooperatively
- **Architecture**: Unix socket IPC, JSON protocol, compile flag `-DENABLE_GAP`
- **Integration**: Hooks in `game_loop()` for state, `GameEventHandler()` for input
- **Status**: Multiplayer companion mode with chat fully functional
## Documentation

- **docs**: Review the ./docs directory for context.

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

### Companion Mode (POC Complete, Architecture Redesign Needed) ⚠️
- **Concept**: Load saved character into multiplayer slot
- **POC Success**: Chat, LLM decisions, combat AI, navigation all proven working
- **Critical Bug**: Commands execute on wrong player due to network routing assumptions
- **Root Cause**: GAP was bolted onto single-player control; needs proper entity control abstraction

### Headless Peer Mode (Future)
- **Concept**: Two separate game instances via TCP/IP
- **Benefits**: Natural multiplayer, independent saves
- **Status**: Planning phase

### POC Evaluation Summary (Sept 2025)
- ✅ **JSON Communication**: Fixed truncation with `num_predict: 200`
- ✅ **LLM Integration**: Combat decisions, navigation, chat all working  
- ✅ **Multi-Tech Stack**: DevilutionX ↔ GAP ↔ MCP ↔ Ollama successfully integrated
- ✅ **AI Behavior**: Threat assessment, combat priorities, survival reflexes functional
- ❌ **Architecture Limitation**: Network routing sends companion commands to wrong player
- **Lesson Learned**: Need proper entity control abstraction for scalable companion system

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

## Combat Debug Investigation History

### Sept 2025: Command Routing Bug Identified ✅
**Issue**: Companion AI generates correct intents but commands execute on wrong player
**Root Cause**: GAP architecture evolved from single-player to companion mode without updating network command routing

**Debug Evidence**:
```
GAP: GetControlledPlayer - controlled_slot=1 MyPlayerId=
GAP: ExecuteMove - Controlling player 1 (name: Rodney) at pos (2,/) to target (53,44)
⚔️ SENDING TO LLM: 5 monsters, priority target: ID 7 Skeleton (Action: ATTACK_NOW)
🔍 RAW OLLAMA RESPONSE: {"intent": {"type": "intent", "action": "attack", "params": {"x": 76, "y": -1}}}
```

**Architecture Issue**:
- ✅ `GetControlledPlayer()` correctly returns slot 1 (companion)
- ✅ LLM generates valid attack intents for companion
- ❌ `NetSendCmdLoc(companion_id, ...)` routes commands to main player instead of companion
- **Fix needed**: Update GAP network command routing for proper player slot isolation

### Dec 2024: Monster Visibility Investigation ✅ (RESOLVED)
**Issue**: Companion not detecting monsters (resolved - was AI processing bug)
**Solution**: Enhanced debug logging revealed companion receives full monster data correctly

## Next Architecture: First-Class Entity Control System

### Problem with Current Architecture
- GAP was designed for single-player AI control (AI controls main player)
- Companion mode was bolted on using multiplayer slots
- Network command routing assumes single player context
- Results in commands executing on wrong player

### Proposed Solution: Entity Controller Abstraction
```
Human Input    → EntityController[0] → Player 0 Actions
GAP Protocol   → EntityController[1] → Player 1 Actions  
GAP Protocol   → EntityController[2] → Player 2 Actions
GAP Protocol   → EntityController[3] → Player 3 Actions
```

### Benefits
- **Clean separation**: Each entity has its own control interface
- **Scalable**: Support 1→3+ companions without architectural changes  
- **No network hacks**: Direct entity manipulation instead of fighting multiplayer routing
- **Diablo 2 style**: Similar to mercenary/hireling system
- **Future-proof**: Supports different control types (human, AI, scripted)

### Implementation Notes
- Create `EntityController` abstract interface
- `HumanController` for keyboard/mouse input
- `GapAIController` for LLM/GAP protocol
- `EntityManager` to coordinate all controllers
- Direct player state manipulation without network commands

## Technical Debt
- **PRIORITY: Implement first-class entity control system** 🚨
- Replace custom JSON with nlohmann/json
- Add GAP config file  
- Implement state delta compression
- ~~Fix MCP server movement bug~~ ✅ Fixed with navigation integration
- ~~Fix JSON truncation in LLM responses~~ ✅ Fixed with `num_predict: 200`
- ~~Investigate GAP companion monster visibility~~ ✅ Resolved - monsters visible to companion

