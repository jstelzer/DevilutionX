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

### Phase 2 Priorities: Combat & Enhanced State
1. **Combat intents**:
   - Attack specific monsters by ID
   - Cast spells at locations
   - Use potions when health is low
   
2. **Enhanced monster state**:
   - Monster type names (not just "MON")  
   - Accurate HP percentages
   - Distance calculations
   - Threat assessment (hostile vs neutral)

3. **Combat agent demo**:
   - Simple "kiting" behavior 
   - Target closest monster
   - Retreat when health is low
   - Use health potions automatically

### Phase 3 Priorities: Inventory & Items  
1. **Inventory state**:
   - Equipment slots
   - Inventory grid contents
   - Item identification and stats
   
2. **Item intents**:
   - Pick up items by ID
   - Use/equip items
   - Drop unwanted items
   - Manage inventory space

3. **Loot agent demo**:
   - Pick up valuable items
   - Manage inventory space
   - Prioritize upgrades

### Phase 4: Advanced AI Integration
1. **LLM Interface Layer**:
   - Convert game state to natural language descriptions
   - Parse natural language commands into intents
   - Multi-turn conversation about game state
   
2. **NVIDIA LLM Integration**:
   - **Ollama + modest model**: Local inference via ollama API
   - **MCP agent pattern**: Treat GAP socket like MCP resource - bi-directional JSON pipe instead of webpage fetching
   - **Personality system**: Prompt engineering for expert vs novice playstyles
   - **Character metadata embedding**: Available characters, stats, gear in context
   - **Debug mode leverage**: Use debug commands for character leveling, gear spawning during AI development
   - Context window management for long games

3. **Advanced Behaviors**:
   - Quest completion strategies
   - Dungeon exploration with memory
   - Cooperative multiplayer AI teammates
   - Learning from player demonstrations

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

### Current Limitations & Known Issues
- **State publishing rate**: Fixed at every 2 ticks (could be configurable)
- **Monster state**: Only basic info (position, HP%), no type names or abilities yet
- **No attack intents**: Movement only, combat system not implemented
- **Custom JSON parser**: Works but could be replaced with nlohmann/json for robustness
- **Error handling**: Basic, could be more robust for production use

### Testing Notes
- **Agent requires player movement first**: Character must be manually moved before AI takes control
- **Password parameter**: `python3 test_gap_agent.py --password "your_password"`
- **Debug output**: Game shows "GAP: Agent connecting" in console when client connects

### Technical Debt & Improvements
- Replace custom JSON with nlohmann/json for better performance
- Add configuration file for GAP settings (socket path, tick divisor, etc.)
- Implement state delta compression for efficiency
- Add more robust error handling and reconnection logic
- Performance profiling and optimization
- (Future) Separate AI character support with headless mode


### Refinement ideas...

4) State packing (performance)

Keep “nearby only”, but add IDs + name for monsters now (tiny cost, huge agent win).

Diablo has type indices → emit {"id": mId, "type": "Skeleton Archer", …}.

Include tile walkability (1-bit grid around player) or a blocked flag on move_to reject → fewer failed moves.

5) Threading model (don’t stall the sim)

IPC accept/read on a small worker thread; enqueue intents to a lock-free ring.

Apply intents at start of tick; publish state after sim, every N ticks (e.g., 2 → ~30 Hz if 60 Hz sim).

Phase 2: Combat—concrete hooks

You already wrote the right goals; here are the engine touchpoints to keep changes minimal:

Attack target by ID

Resolve monsterId → world index safely.

Use the same helper as click-to-attack (so pathing + range checks happen).

Net path: NetSendCmdParamXxx variant Diablo uses for attack orders.

Cast at tile

Slot index → spell id → call the engine “cast at tile” helper; net-send equivalent.

Use potion

Belt slot → UseInvItem()/belt helper with cooldown checks; net-send if needed.

State additions (very small, very useful):

"player":{"hp":..,"hp_max":..,"pos":[x,y],"belt":[{"t":"heal","n":2},{"t":"mana","n":1},null,null]},
"nearby":{"monsters":[{"id":42,"type":"Skeleton","hp_pct":60,"pos":[..]}]}

Phase 3: inventory (keep it thin)

Start with belt + ground items only.

pickup{id} should reject out-of-range with "invalid_position".

Defer full grid until combat is stable.

LLM integration (local NVIDIA)

Run reflex (heals/kite) outside the LLM at 5–10 Hz → guaranteed safety.

Let Ollama (7–8B Q4 on your card) act as a coach at 0.5–2 Hz: pick target, direction, say text.

Emit one non-critical intent per LLM cycle; reflex can pre-empt with use_potion/stop.

Minimal coach loop contract (clean and stable):

// agent output
{"cmd":"move_to","x":..,"y":..}
{"cmd":"attack","target_id":..}
{"cmd":"use_potion","slot":1}
{"cmd":"say","text":"kite west"}

Testing checklist (fast confidence)

Spawn in town → move_to grid walk.

Enter dungeon → move_to around corners (pathfinder gets exercised).

Spawn 1 skeleton → attack cycles with correct range (no spam).

Simulate low HP → use_potion fires under rate limit.

Multiplayer host → second client movement still fine (no desync).

Small repo polish

Swap custom JSON for nlohmann/json when you touch parsing next.

Add GAP_TICK_DIVISOR env/flag.

Add a kill-switch key (e.g., F9) to stop consuming intents immediately.

Log (tick, seq, intent, result) to a ring buffer (easy post-mortems).
