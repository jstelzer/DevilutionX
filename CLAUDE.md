# DevilutionX GAP project

Review GAP.md for the concept.

I would like to run an LLM on my nvidia card and play diablo with it.

Evaluate the code in Source.

## Claude's Evaluation

This is a fascinating project! The GAP (Game Agent Protocol) concept is well-designed and practical. After reviewing the DevilutionX source and your GAP specification, here's my assessment:

### Strengths of the Current Approach
1. **Pragmatic design**: Starting with IPC/pipes is smart - avoids network complexity
2. **Non-invasive**: The compile flag approach (`-DENABLE_GAP`) keeps it clean
3. **Right integration points**: You've identified the correct hooks:
   - `game_loop()` at diablo.cpp:3361 for state extraction
   - `GameEventHandler()` at diablo.cpp:715 for input injection
4. **Sensible rate limiting**: Publishing state every N ticks prevents overwhelming the LLM

### About the ECS Wrapper Idea

What if we added an ECS wrapper and used that to coordinate state with the LLM?
It might not be ECS in the traditional sense, but we could wire in the existing structs/events such that ECS or some other system could observe and serialize everything.

**This is a solid architectural pattern!** While not traditional ECS, creating an observation layer makes sense:

### Recommended Approach: Lightweight Observer Pattern

Instead of full ECS, consider a **State Observer/Serializer** layer:

```cpp
// Source/gap/gap_observer.h
class GapStateObserver {
    // Register interest in specific game objects
    void WatchPlayer(PlayerStruct* player);
    void WatchMonsters(MonsterStruct* monsters, int count);
    void WatchTiles(int radius);
    
    // Collect deltas since last tick
    json CollectStateSnapshot(int tick);
    json CollectStateDelta(int lastTick);
};
```

### Benefits Over Direct Struct Access
1. **Decoupling**: Game code doesn't need to know about serialization
2. **Performance**: Can track only what changed (deltas)
3. **Flexibility**: Easy to add/remove observed data without touching game code
4. **LLM-friendly**: Can pre-process data into formats LLMs understand better

### Integration Strategy

Phase 1 MVP adjustments:
1. Create thin observer wrappers around existing structs
2. Use dirty flags to track changes efficiently
3. Serialize only visible/relevant state (20-tile radius as you planned)

### For Your NVIDIA LLM Setup

Consider these optimizations:
1. **Batch state updates**: LLMs work better with context windows
2. **Semantic compression**: Convert game state to natural language when beneficial
3. **Action planning**: Let LLM output high-level goals, translate to low-level intents

Example flow:
```
Game State → Observer → Semantic State → LLM → High-level Plan → Intent Translator → Game Actions
```

### Potential Challenges
1. **Latency**: Local LLM inference might be 50-200ms per decision
2. **Context size**: Full state might exceed LLM context window
3. **Coordination**: Async LLM responses vs game tick timing

### Fun Factor Assessment
**This will definitely be fun!** Watching an AI companion navigate dungeons, learn from mistakes, and develop strategies will be entertaining. Consider adding:
- Personality modes (aggressive, cautious, greedy)
- Learning from player behavior
- Natural language narration of its decisions

The project is very achievable with your phased approach. Start simple with movement in town, then gradually add complexity. The observer pattern will keep it maintainable as you expand.

## Notes

* When generating scripts/python note I'm on linux so only use \n not \r\n for line ending.s

## Post MVP

We're at a state where the client can influence the characters movement. So the protocol is working.

### Phase 1 MVP: ✅ COMPLETE
- ✅ Basic IPC via Unix sockets (`/tmp/devilutionx-gap.sock`) Optional: allow `XDG_RUNTIME_DIR` (e.g., `$XDG_RUNTIME_DIR/devilutionx-gap.sock`) when present.
- ✅ JSON protocol with handshake and password support
- ✅ Game state publishing (player position, HP, monsters, items, UI state)
- ✅ Movement intent processing with proper pathfinding
- ✅ Python test agent with square movement pattern
- ✅ Network compatibility for multiplayer games

**Status**: AI can successfully read game state and control character movement. Protocol is fully functional!

### Phase 2: Combat & Enhanced State ✅ COMPLETE
1. **Combat intents**:
   - ✅ Attack specific monsters by ID
   - ✅ Attack positions (for area attacks)
   - ✅ Automatic weapon type detection (melee vs ranged)
   - ⏳ Cast spells at locations (TODO: Phase 3)
   - ⏳ Use potions when health is low (needs inventory support)
   
2. **Enhanced monster state**:
   - ✅ Monster names (actual names like "Skeleton", "Zombie")
   - ✅ Accurate HP values and percentages
   - ✅ Distance calculations (Chebyshev distance)
   - ✅ Armor class values
   - ✅ Minion detection (friendly vs hostile)

3. **Combat agent demo**:
   - ✅ Target closest hostile monster
   - ✅ Attack when in range with proper timing
   - ✅ Tactical hit-and-run movement (retreat after attacks)
   - ✅ Resume engagement after retreat cooldown
   - ✅ Dynamic movement patterns during combat
   
4. **Enhanced Vision System** (NEW):
   - ✅ Light-radius based vision (authentic to player experience)
   - ✅ Walkability grid within light radius (walls, obstacles)
   - ✅ Detailed ground item information (potions, gold, equipment)
   - ✅ Dynamic vision range (scales with player's light radius)

### Phase 3: LLM Integration & MCP Agent ⭐ MILESTONE REACHED! ✅

**MAJOR BREAKTHROUGH**: Successfully connected Ollama LLM to GAP protocol with intelligent real-time gameplay!

1. **Enhanced GAP Protocol** ✅ COMPLETE:
   - ✅ Light-radius based vision system (authentic Diablo experience) 
   - ✅ Stair/portal detection for level progression
   - ✅ Interactive objects (chests, barrels) within exploration radius
   - ✅ Map exploration memory and systematic area clearing
   - ✅ Detailed item information (names, types, values)
   - ✅ Rich monster data for tactical decisions

2. **MCP Agent Architecture** ✅ PRODUCTION READY:
   - ✅ MCP server bridges GAP socket ↔ Ollama API seamlessly
   - ✅ Structured prompts with complete GAP protocol documentation
   - ✅ Direct JSON intent generation (no translation layers needed)
   - ✅ Personality system with 4 distinct playstyles
   - ✅ Comprehensive logging and error handling

3. **Intelligent Pathfinding & Navigation** ✅ WORKING:
   - ✅ **Hybrid LLM + Python pathfinding**: Strategic decisions (LLM) + reliable execution (Python)
   - ✅ **Incremental movement**: Breaks long distances into manageable 3-5 tile steps
   - ✅ **Obstacle avoidance**: Uses walkable grid to navigate around buildings/walls
   - ✅ **Dynamic waypoint calculation**: Automatic intermediate targets for complex navigation
   - ✅ **Stuck detection**: Detects when AI is blocked and provides alternative routes
   - ✅ **Context-aware**: LLM receives navigation state (blocked paths, suggested waypoints)

4. **Combat Intelligence** ✅ WORKING WELL:
   - ✅ **Combat-first priority**: Never ignores monsters when under attack
   - ✅ **Enemy seeking**: Actively searches for and engages nearby monsters
   - ✅ **Range awareness**: Proper melee distance management (1-2 tiles for attacks)
   - ✅ **Threat assessment**: Prioritizes closest/most dangerous enemies
   - ✅ **Multi-layered protection**: Both LLM prompt guidance + Python safety nets

5. **Map Exploration & Progression** 🔄 PARTIAL - NEEDS IMPROVEMENT:
   - ⚠️ **Complex pathfinding**: Gets stuck on complex routes, needs better navigation
   - ⚠️ **Exploration efficiency**: Doesn't systematically explore areas on its own
   - ✅ **Infrastructure ready**: Memory tracking and object detection implemented
   - ✅ **Level progression detection**: Can detect stairs/portals but doesn't navigate to them reliably

**Current Performance**: AI successfully engages in combat and seeks out nearby enemies. Complex pathfinding and systematic exploration still need improvement - AI tends to get stuck on complex routes and doesn't explore efficiently on its own.

**Usage**: `python3 tools/gap/mcp_server.py --model qwen2.5:3b --password "your_password"`

**Recommended Models**: 
- **Fast**: qwen2.5:3b (1.9GB) - Excellent real-time performance
- **Balanced**: llama3.2:latest (2.0GB) - Good speed/intelligence balance  
- **Powerful**: llama3.1:8b - Higher intelligence but slower responses

### Phase 4: Advanced Features & Polish
1. **Spell casting intents** (current protocol gap)
2. **Inventory management** (pick up items, use potions)
3. **Quest completion strategies**
4. **Dungeon exploration with memory**
5. **Cooperative multiplayer AI teammates**

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

### Architectural Decision: Shared Character Control
**Decision**: Continue using player's existing character for AI development rather than implementing separate AI character support immediately.

**Rationale**:
- Test AI capabilities with geared, high-level characters
- Skip character creation/leveling automation complexity  
- Faster iteration on AI behaviors and decision-making
- Immediate feedback on AI performance in real scenarios
- Defer infrastructure overhead until AI proves competent

**Timeline**: Will revisit separate AI characters as Phase 3.5/4 after proving AI decision-making capabilities.

### Long-term Vision: Built-in AI Companion System
**Goal**: Integrate GAP as a core DevilutionX feature that ships with the game.

**Player Experience**:
- **Settings menu option**: "Enable AI Companion" (default: off)
- **Personality selection**: Choose from pre-built AI personalities (Cautious, Aggressive, Explorer, etc.)
- **Difficulty scaling**: AI adapts to player skill level
- **Optional feature**: Players can enjoy classic Diablo or enhanced co-op experience

**Benefits**:
- **Accessibility**: Solo players get co-op experience
- **Learning tool**: New players can watch AI demonstrate strategies  
- **Replayability**: Different AI personalities create varied gameplay
- **No external dependencies**: Works out-of-the-box with bundled models

### Key Implementation Details (for future reference)
- **Socket path**: `/tmp/devilutionx-gap.sock` (hardcoded, could be configurable)
- **Movement fix required**: Must use `MakePlrPath()` + `NetSendCmdLoc()` for proper pathfinding
- **Player ID validation**: `MyPlayerId >= MAX_PLRS` (not `< 0`, it's unsigned)
- **Multiplayer compatibility**: Password support in handshake, network commands included
- **Build requirement**: `-DENABLE_GAP=ON` compile flag

### Current Status & Next Steps

**✅ COMPLETED (Phase 1-2)**:
- Basic GAP protocol working (IPC, JSON, handshake)
- Movement and attack intents fully functional
- Enhanced vision system with light-radius based spatial awareness
- Tactical combat AI with hit-and-run behavior
- Rich item and monster information for decision-making

**🎯 LLM INTEGRATION COMBAT MILESTONE ACHIEVED! (Phase 3 Partial ✅)**:
The AI successfully demonstrates intelligent combat behavior and enemy engagement. Navigation and exploration systems need further development to achieve full autonomous gameplay. The hybrid architecture (LLM strategy + Python safety) works well for combat scenarios.

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

### Testing Notes
- **Test agents location**: `tools/gap/` directory
- **Basic movement agent**: `python3 tools/gap/test_gap_agent.py --password "your_password"`
- **Enhanced combat agent**: `python3 tools/gap/combat_gap_agent.py --password "your_password"`
- **Combat features**: Tactical movement, target selection, retreat-and-resume behavior
- **Vision system**: LLM-ready spatial awareness with walkability and item data

### Current Limitations & Known Issues
- **Complex pathfinding**: AI gets stuck on complex routes, doesn't navigate efficiently through dungeons
- **Exploration behavior**: Doesn't systematically explore areas without manual guidance
- **Spell casting**: Move and attack work, spell intents not yet implemented
- **Inventory interaction**: Can see items but can't pick them up yet
- **Model dependency**: Performance varies significantly between LLM models (qwen2.5:3b recommended)
- **Long-distance navigation**: Struggles with multi-room pathfinding and level progression

---

## 🎯 COMPANION MODE BREAKTHROUGH - December 2025

**Revolutionary Insight**: Instead of autonomous AI, pivot to **AI Companion Mode** - eliminating massive complexity while creating superior gameplay experience.

### The "Local Character" Approach ✨

**Core Concept**: Let GAP agent control one of your existing saved characters instead of creating separate headless instances.

```
# Future CLI approach
./devilutionx --gap-control-character="MyWarrior" --password="foo" 

# In-game menu approach (future)
[Multiplayer] → [Local Co-op] → [AI Companion: Select Character]
```

**🎉 Benefits Unlocked:**
- **Zero save file complexity** - Uses existing character progression 
- **Natural co-op experience** - Human leads, AI follows and assists
- **Character flexibility** - Swap which character is AI-controlled per session
- **Pathfinding problem solved** - Human handles navigation, AI focuses on combat/support
- **Progression retained** - AI can level up your alts while you play main character

### Companion Behavior Patterns

**🤖 "Follow Me" Mode** (Phase 1):
- AI stays within 5-8 tile radius of player
- Player leads exploration and navigation  
- AI provides combat support and chat interaction
- Natural conversation during dungeon exploration

**⚔️ "Combat Assistant" Mode** (Phase 2):
- Tank AI character draws aggro while player deals DPS
- Support AI character heals/buffs while player attacks
- Ranged AI character provides covering fire
- Tactical coordination without complex pathfinding

**📦 "Resource Manager" Mode** (Phase 3):
- AI handles inventory optimization
- Makes town runs for supplies while player explores
- Manages potion usage and item identification
- Economic decision-making for equipment upgrades

### Implementation Advantages

**Architecture Simplification:**
- **No headless mode complexity** - Uses standard game client
- **No separate save management** - Leverages existing character system
- **No complex exploration AI** - Human provides strategic guidance
- **Focus on fun features** - Combat, chat, cooperation instead of navigation

**Player Experience Enhancement:**
```
Player: "Hey Claude, can you tank while I play my mage?"
AI: "Sure! Switching to your warrior character now."
[AI takes control of warrior, follows player's mage]
AI: "Ready to go - I'll draw enemies while you cast from behind me."
```

**Scalability Path:**
- Phase 1: Single AI companion
- Phase 2: Multiple AI companions (full 4-player party)  
- Phase 3: AI learns player preferences and adapts playstyle
- Phase 4: Advanced coordination and tactical planning

### Impact on Current Work

**✅ Everything Built So Far Remains Valid:**
- Chat integration works perfectly for companion mode
- Combat intelligence translates directly to support roles
- State management scales to companion coordination
- MCP architecture handles follow-me behaviors seamlessly

**🔧 Required Adjustments (Minimal):**
1. Add character selection to MCP server startup
2. Implement basic follow-player behavior (stay within radius)
3. Modify prompts to emphasize cooperation over autonomy
4. Add companion-specific personality modes (tank, support, DPS)

**🚀 Immediate Next Steps:**
1. Test current MCP agent in "follow me" mode 
2. Add distance-based movement (don't wander too far from player)
3. Update prompts for companion personality
4. Prototype character selection system

This approach transforms GAP from **"AI plays alone"** to **"AI adventuring buddy"** - much more compelling and achievable! 🎮

---

## DEVELOPMENT ROADMAP - NEXT STEPS

### Phase 0: Protocol Enhancements (High Impact, Low Effort) ✅ **COMPLETED**
**Target: Robust Foundation - Complete Basic Survival Loop**

**🎉 Phase 0 Implementation Complete!** All 7 Phase 0 tasks have been successfully implemented and validated:

✅ **New GAP Intent Types** - `cast`, `pickup`, `use_potion`, `interact`, `path`, `explore` with full parameter support
✅ **Essential State Additions** - Belt info, spells, objects, and exploration data extraction  
✅ **Survival Reflex System** - Python-based emergency overrides for healing, kiting, and threat response
✅ **Systematic Exploration** - Frontier-based exploration with completion tracking and priority selection
✅ **Robust Navigation** - A* pathfinding with waypoint chunking and stuck detection recovery
✅ **Validation Tests** - 5 comprehensive tests all passing (town exploration, pathfinding, combat survival, emergency healing, door interaction)
✅ **Debug Tools** - Replay logging, performance monitoring, and development utilities

**🗣️ MAJOR: Bidirectional Chat System** ✅ **FULLY FUNCTIONAL** - LLM-powered conversation:
- **Player → AI**: Send any message in game chat - AI sees and understands it
- **AI → Player**: LLM generates personalized responses based on context and conversation
- **Natural conversation**: "How are you?" → "I'm doing well, thanks for asking! Ready to explore the dungeon together!"
- **Context-aware**: AI responds appropriately to specific questions and comments
- **Intelligent fallbacks**: System gracefully handles invalid intents by prioritizing chat responses
- **Real-time communication**: No alt-tabbing needed - chat directly in-game!

**Chat Commands** (traditional `!ai` format also supported):
- `!ai help` - Show available commands
- `!ai status` - Display AI status and state  
- `!ai debug` - Debug information
- `!ai config` - Configure AI settings

**Status**: The GAP AI system has been transformed from basic tactical combat to a robust, systematic dungeon-clearing agent ready for gameplay.

#### A. New Intent Types (Lock Protocol v0.3)
```json
// Enhanced interaction capabilities  
{"type":"intent","data":{"cmd":"cast","slot":1,"x":52,"y":47,"targetTick":12346}}
{"type":"intent","data":{"cmd":"pickup","id":16}}  // item by ID
{"type":"intent","data":{"cmd":"use_potion","kind":"hp"}}  // or {"slot":0}
{"type":"intent","data":{"cmd":"interact","id":301}}  // doors/chests/stairs
{"type":"intent","data":{"cmd":"path","x":80,"y":12}}  // long-range pathfinding
{"type":"intent","data":{"cmd":"explore"}}  // frontier-based exploration
```

#### B. Essential State Additions
```json
"player": {
  "belt": [{"t":"hp","n":2},{"t":"mp","n":1},null,null],
  "spells": {"slot1":"Firebolt","slot2":"TownPortal"}
},
"objects": [
  {"id":301,"kind":"chest","pos":[49,44],"locked":false},
  {"id":302,"kind":"stairs_down","pos":[60,15]}
],
"exploration": {
  "seen_mask": "RLE_encoded_bitstring",  // memory efficient
  "frontiers": [[x,y], [x,y]]  // explorable boundary tiles
}
```

#### C. Survival Reflex System (Python Layer)
```python
class SurvivalReflexes:
    """Critical survival logic that overrides LLM decisions"""
    def __init__(self):
        self.last_potion_time = 0
        self.potion_cooldown = 500  # ms
        
    def check_emergency_actions(self, state):
        """Non-negotiable survival responses"""
        player = state['player']
        
        # Emergency healing
        if player['hp'] / player['hp_max'] < 0.25:
            if time_since_last_potion >= self.potion_cooldown:
                return {"type":"intent","data":{"cmd":"use_potion","kind":"hp"}}
        
        return None  # No emergency action needed
```

#### D. Systematic Exploration Algorithm
```python
def exploration_step(state):
    """Frontier-based exploration for complete level coverage"""
    seen_mask = decode_seen_mask(state['exploration']['seen_mask'])
    
    # Find frontier cells: unseen but adjacent to seen walkable tiles
    frontiers = find_exploration_frontiers(seen_mask)
    
    if not frontiers:
        return None  # Exploration complete
    
    # Select closest frontier by A* distance  
    current_pos = state['player']['pos']
    best_frontier = min(frontiers, key=lambda f: astar_distance(current_pos, f))
    
    return {"type":"intent","data":{"cmd":"path","x":best_frontier[0],"y":best_frontier[1]}}
```

#### E. Validation Tests (Run Tonight)
1. **Town Exploration**: Spiral "explore" fills Tristram square without getting stuck
2. **Pathfinding Around Obstacles**: A* reaches visible chest around walls  
3. **Basic Combat Survival**: 1v1 skeleton with proper kiting behavior
4. **Emergency Healing**: Pre-pot at low health, respect cooldown
5. **Door Interaction**: Navigate through doors to reach targets

**Expected Result**: Robust, non-crashing AI that survives encounters and systematically clears levels

---

### Phase 1: Core Exploration (High Impact, Medium Effort)
**Target: Systematic Level Clearing**
- Enhanced memory system for visited areas
- Frontier tile detection and prioritization  
- LLM prompts with completion percentage context
- **Expected Result**: AI clears 95%+ of each level before advancing

### Phase 2: Strategic Intelligence (High Impact, High Effort)
**Target: Goal-Oriented Behavior**
- Quest state tracking in GAP protocol
- Goal hierarchy system (kill Diablo → clear levels → explore areas)
- Strategic prompting with mission context  
- **Expected Result**: AI understands its overarching mission and makes strategic decisions

### Phase 3: Spatial Intelligence (Medium Impact, High Effort)  
**Target: Advanced Navigation**
- Room detection and analysis system
- Landmark-based navigation graphs  
- Tactical positioning for combat
- **Expected Result**: AI navigates complex layouts efficiently and uses terrain tactically

### Phase 4: Social Intelligence (Medium Impact, Medium Effort)
**Target: Town NPC Integration**  
- Town NPC locations and services in state
- Economic decision-making for purchases
- Resource management strategies
- **Expected Result**: AI manages resources intelligently and utilizes town services strategically

### Phase 5: Communication Layer (Low Impact, Low Effort)
**Target: Human-AI Collaboration**
- Chat integration for strategy discussion
- Decision explanation system
- Strategic consultation prompts  
- **Expected Result**: Enhanced debugging and collaborative gameplay experience

---

## TECHNICAL ARCHITECTURE

### State Management Scaling
```python
# Future: Modular state components
class GapStateManager:
    def __init__(self):
        self.components = {
            'player': PlayerStateComponent(),
            'combat': CombatStateComponent(), 
            'exploration': ExplorationStateComponent(),
            'inventory': InventoryStateComponent(),
            'social': SocialStateComponent()  # NPCs, multiplayer
        }
    
    def get_contextual_state(self, situation):
        """Return only relevant state for current situation"""
        if situation == 'combat':
            return ['player', 'combat']
        elif situation == 'town':
            return ['player', 'inventory', 'social']  
        else:
            return ['player', 'exploration']
```

### Performance Optimization Strategies
1. **Delta State Updates**: Only send changes since last tick
2. **Semantic Compression**: Convert raw game data to LLM-friendly summaries
3. **Predictive Caching**: Pre-compute likely LLM responses for common situations
4. **Parallel Processing**: Run exploration analysis while LLM processes combat decisions

---

### Technical Debt & Improvements
- Replace custom JSON with nlohmann/json for better performance
- Add configuration file for GAP settings (socket path, tick divisor, etc.)
- Implement state delta compression for efficiency
- Add more robust error handling and reconnection logic
- Performance profiling and optimization
- (Future) Separate AI character support with headless mode

