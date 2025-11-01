# GAP: Game Agent Protocol (v0.3 Draft)

**A lightweight protocol for AI agents to play games cooperatively with humans**
**License:** Spec under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/); reference implementations under [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0).

---

## 🎯 Protocol Evolution

**v0.1**: JSON protocol with monolithic LLM agent
**v0.2**: DSL protocol with single specialized agent
**v0.3**: Multi-agent council architecture ← **Current**

---

## 🚀 Implementation Status (November 2025)

### ✅ Completed: DSL Protocol (Compact Alternative to JSON)

**Motivation:** Original JSON protocol (1-2KB per state) was too verbose for LLM context windows. DSL reduces state size by 10x.

**Format:**
```
T=12345 F=2 ME=34,18,72,33 PLYR=51,54 M=12@38,16,55,1;19@36,17,20,1 L=71@35,19,10
```

**Benefits:**
- 100-200 bytes vs 1-2KB JSON (10x smaller)
- 80-120 LLM tokens vs 400-600 (5x fewer)
- 200-500ms decisions vs 500-2000ms (2-4x faster)
- Simple parsing, easy to debug

**Agent Stack:**
- `dsl_agent.py` - Main LLM loop with Ollama integration
- `dsl_parser.py` - State parsing and LLM prompt generation
- `chat_handler.py` - Async template-based chat (non-blocking)
- `memory_store.py` - SQLite persistent memory
- Grammar constraints enforce valid DSL output from LLM

**Status:** ✅ **Commands validated and sent successfully**

### ⚠️ Current Blocker: Entity Control Routing

**Problem:** Commands execute on wrong player entity
- Agent generates valid commands: `AT 164`, `MV 78 77`
- Commands sent via socket successfully
- Game receives commands but routes to main player instead of companion
- Companion frozen at position, never executes commands

**Evidence:**
```
📤 Command: AT 164 (took 0.15s)
📤 Sent: AT 164...
State: tick=1674 pos=(78,78)  ← companion stuck
State: tick=1734 pos=(78,78)  ← still frozen
State: tick=1794 pos=(78,78)  ← never moves
```

**Root Cause:** GAP architecture evolved from single-player control to companion mode without updating network command routing (see CLAUDE.md for details)

**Next Step:** Fix entity controller abstraction to route commands to correct player slot

---

## 🌟 Evolution to Multi-Agent Council (v0.3)

### The Paradigm Shift

**Problem with Monolithic Agents:**
- Single LLM trying to balance combat, survival, loot, exploration, and cooperation
- Large context windows (400-600 tokens) causing decision slowness
- Conflicting priorities causing decision paralysis
- No specialization → mediocre performance across all domains

**Solution: Specialist Agent Council**

Instead of one LLM doing everything, we have a **council of specialist agents**, each expert in their domain:

```
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator                          │
│           (Receives game state, routes to agents,        │
│            collects votes, picks optimal action)         │
└────────────┬────────────────────────────────────────────┘
             │
     ┌───────┴────────┬─────────────┬──────────────┐
     ▼                ▼             ▼              ▼
┌──────────┐   ┌───────────┐  ┌──────────┐  ┌──────────┐
│ Combat   │   │ Healing   │  │ Movement │  │  Loot    │
│ Agent    │   │ Agent     │  │ Agent    │  │  Agent   │
│ (50 tok) │   │ (30 tok)  │  │ (80 tok) │  │ (40 tok) │
└──────────┘   └───────────┘  └──────────┘  └──────────┘
     │                │             │              │
     └────────────────┴─────────────┴──────────────┘
                      │
              Weighted Votes:
              AT 27: 0.85 (Combat)
              USE 0: 0.95 (Healing) ← WINS
              MV 72,81: 0.70 (Movement)
              PK 71: 0.60 (Loot)
```

### Generic Agent Types (Game-Agnostic)

#### Core Action Agents
- **Combat Agent**: Offensive decision-making (attack, special abilities)
- **Defensive Agent**: Survival decisions (healing, shield, dodge, retreat)
- **Movement Agent**: Positioning and navigation
- **Resource Agent**: Loot/item collection

#### Situational Agents (Context-Dependent)
- **Social Agent**: Town/NPC interactions, trading
- **Progression Agent**: Character development (stats, skills, upgrades)
- **Exploration Agent**: Map navigation, quest objectives
- **Inventory Agent**: Item management, equipment optimization

#### Meta-Agents (Influence Others)
- **Risk Assessment Agent**: Evaluates danger level, informs all other agents
- **Strategy Agent**: Long-term planning, quest priorities

### Council Benefits

1. **Prompt Isolation**: 30-80 tokens per agent vs 400-600 monolithic
2. **Parallel Execution**: Run agents concurrently (we have CPU to spare)
3. **Clear Priorities**: Orchestrator enforces hierarchy (survival > combat > loot)
4. **Extensibility**: Add new agents without touching existing ones
5. **Debuggability**: See each agent's vote and orchestrator's reasoning
6. **Model Flexibility**: Fast 3B models for simple agents, 8B for complex ones

### Agent Communication Pattern

```python
class SpecialistAgent:
    """Base pattern for all agents"""

    def evaluate(self, state: GameState) -> WeightedRecommendation:
        """
        Evaluate game state and return weighted recommendation.

        Args:
            state: Minimal relevant state for this agent

        Returns:
            WeightedRecommendation(
                action: str,        # Game-specific command
                weight: float,      # 0.0-1.0 confidence
                reasoning: str      # Optional debug info
            )
        """
        pass

class Orchestrator:
    """Routes state to agents, collects votes, picks winner"""

    def decide(self, full_state: GameState) -> Action:
        # 1. Meta-agents run first (risk assessment)
        risk = self.risk_agent.evaluate(full_state)

        # 2. Situational context (in town vs combat vs exploring)
        context = self.determine_context(full_state)

        # 3. Run relevant agents in parallel
        recommendations = self.run_agents_parallel(full_state, context)

        # 4. Apply priority hierarchy
        #    Example: healing > combat > resource > movement > exploration
        return self.apply_hierarchy(recommendations, risk)
```

### Dormancy System

Agents can be **active**, **dormant**, or **disabled** based on context:

```python
# Combat agent dormant in safe town
if state.in_safe_zone:
    combat_agent.dormant = True

# Social agent only active in town
if not state.in_town:
    social_agent.dormant = True

# Progression agent only active on level-up
if not state.level_up_available:
    progression_agent.dormant = True
```

This prevents wasting LLM calls on irrelevant decisions.

### Priority Hierarchy (Example)

```
1. CRITICAL (overrides all): Defensive agent (survival)
2. HIGH: Combat agent (if enemies nearby)
3. MEDIUM: Resource agent (if safe)
4. LOW: Movement agent (always available as fallback)
5. LOWEST: Exploration agent (when very safe)
```

Orchestrator uses weighted scoring:
```
final_score = agent_weight * priority_multiplier * context_modifier
```

### Multi-Agent vs Monolithic Comparison

| Aspect | Monolithic Agent | Multi-Agent Council |
|--------|-----------------|---------------------|
| Context size | 400-600 tokens | 30-80 tokens each |
| Decision speed | 200-500ms | 50-200ms per agent (parallel) |
| Specialization | Jack of all trades | Expert in one domain |
| Priority conflicts | Hard to resolve | Clean hierarchy |
| Extensibility | Modify giant prompt | Add new agent |
| Debugging | "Why did it do that?" | See all agent votes |
| Model requirements | Need smart 8B+ model | Can use fast 3B models |
| Failure mode | Indecision/freeze | Fallback to movement agent |

---

## 1. Vision & Scope

GAP enables AI agents to act as co-op partners in games. The protocol prioritizes:

- **Practical implementation** over theoretical perfection
- **Multi-agent architecture** for specialized decision-making
- **Minimal invasiveness** to existing game code
- **Game-agnostic design** (proven with DevilutionX, applicable to any game)
- **Local-first** operation before network support

### 1.1 Design Principles

1. **Modularity**: Specialist agents for different game aspects
2. **Composability**: Agents communicate through weighted recommendations
3. **Adaptability**: Agents activate/dormant based on game context
4. **Extensibility**: Add new agents without changing protocol
5. **Debuggability**: Transparent agent voting and orchestration logic

### 1.2 Non-Goals for v0.3
- Perfect AI gameplay (good enough cooperation is the goal)
- Real-time competitive play (co-op focus)
- Production-grade security (research/hobbyist focus)
- Cross-network agent hosting (local execution only)

---

## 2. Architecture Overview

### 2.1 Multi-Agent Council Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                         Game Process                           │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Game Loop (variable tick rate)                          │  │
│  │ - Extract state → DSL format                            │  │
│  │ - Send via IPC                                          │  │
│  │ - Receive command                                       │  │
│  │ - Execute action                                        │  │
│  └──────────────────┬──────────────────────────────────────┘  │
└─────────────────────┼─────────────────────────────────────────┘
                      │ DSL State (100-200 bytes)
                      │ "T=123 F=2 ME=34,18,72,33 M=12@38,16..."
                      ▼
┌───────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                          │
│                                                                 │
│  1. Receive game state                                         │
│  2. Distribute to relevant agents (parallel)                   │
│  3. Collect weighted recommendations                           │
│  4. Apply priority hierarchy                                   │
│  5. Return winning action                                      │
│                                                                 │
└──┬────────┬────────┬────────┬────────┬────────┬────────┬──────┘
   │        │        │        │        │        │        │
   ▼        ▼        ▼        ▼        ▼        ▼        ▼
┌──────┐ ┌───────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Combat│ │Healing│ │ Move │ │ Loot │ │ Town │ │Stats │ │Danger│
│Agent │ │Agent  │ │Agent │ │Agent │ │Agent │ │Agent │ │Agent │
│      │ │       │ │      │ │      │ │      │ │      │ │(Meta)│
│50tok │ │30tok  │ │80tok │ │40tok │ │60tok │ │50tok │ │100tok│
└──┬───┘ └───┬───┘ └───┬──┘ └───┬──┘ └───┬──┘ └───┬──┘ └───┬──┘
   │         │         │        │        │        │        │
   └─────────┴─────────┴────────┴────────┴────────┴────────┘
                             │
                   Weighted Recommendations:
                   {
                     "AT 27": 0.85,    // Combat
                     "USE 0": 0.95,    // Healing ← Wins
                     "MV 72,81": 0.70, // Movement
                     "PK 71": 0.60     // Loot
                   }
                             │
                             ▼
┌───────────────────────────────────────────────────────────────┐
│                         Game Process                           │
│                     Execute: USE 0                             │
│                   (Drink health potion)                        │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 Game Integration Points

GAP integrates at three levels in the game engine:

1. **Game Loop**
   - Extract state after world update
   - Encode to compact DSL format
   - Send to orchestrator via IPC
   - Receive command
   - Execute action before next tick

2. **State Extraction**
   - Player position, health, mana
   - Nearby entities (monsters, items, NPCs)
   - Context flags (in_town, in_combat, level_up_available)
   - Inventory/belt state

3. **Command Execution**
   - Parse DSL command (AT/MV/USE/PK/TALK/STAT)
   - Validate against game rules
   - Execute via existing game systems
   - Respect UI state machine

---

## 3. Protocol Design

### 3.1 Transport Layer

**Phase 1 (MVP):** Named pipes or Unix domain sockets
- Path: `/tmp/devilutionx-gap.sock` (or Windows named pipe)
- Format: Length-prefixed JSON messages (4-byte LE length + JSON)
- No authentication needed (local only)

**Phase 2 (Future):** WebSocket upgrade
- Allows remote agents and web-based tools
- Add TLS and bearer token auth

### 3.2 Tick Synchronization

**Problem:** DevilutionX uses variable tick rates (20-50 Hz configurable)

**Solution:** Agent operates in "follower mode"
- Game publishes state at its native tick rate
- Each state message includes tick number and timestamp
- Agent can send intents with target tick for scheduling
- Agent adapts to game's actual tick rate dynamically

```json
{
  "type": "state",
  "tick": 45123,
  "tick_rate": 30,  // Current game tick rate
  "timestamp": 1735432456789,
  "data": { ... }
}
```

### 3.3 Rate Limiting Strategy

Respect game's input processing limits:
- **State messages:** Published every N game ticks (configurable, default 2)
- **Intent rate:** Max 1 intent per 2 game ticks
- **Intent queue:** Max 3 pending intents
- **Coalescing:** Combine redundant movement intents

---

## 4. Message Protocol

### 4.1 Initialization Handshake

```json
// Agent → Game
{
  "type": "hello",
  "version": "0.2.0",
  "capabilities": ["move", "attack", "use_item"]
}

// Game → Agent
{
  "type": "hello",
  "version": "0.2.0",
  "tick_rate": 30,
  "state_divisor": 2,  // State sent every 2 ticks
  "game_mode": "single_player",
  "capabilities": ["move", "attack", "use_item", "cast_spell"]
}
```

### 4.2 State Message (Game → Agent)

**Minimal viable state for proof-of-concept:**

```json
{
  "type": "state",
  "tick": 45123,
  "tick_rate": 30,
  "timestamp": 1735432456789,
  "data": {
    "player": {
      "hp": 72,
      "hp_max": 100,
      "mana": 40,
      "mana_max": 90,
      "pos": [48, 52],  // Tile coordinates
      "level": 3,       // Dungeon level
      "in_town": false
    },
    "nearby": {
      // Only send entities within 20 tiles
      "monsters": [
        {"id": 42, "type": "SK", "pos": [51, 54], "hp_percent": 60}
      ],
      "items": [
        {"id": 101, "pos": [45, 50]}  // No type info initially
      ],
      "other_players": []  // For future multiplayer
    },
    "ui_state": {
      "in_menu": false,
      "in_store": false,
      "can_act": true
    }
  }
}
```

### 4.3 Intent Message (Agent → Game)

```json
{
  "type": "intent",
  "action": "move",  // move|attack|use_potion|pickup
  "params": {
    "x": 50,
    "y": 55
  },
  "target_tick": 45125  // Optional: schedule for future tick
}
```

### 4.4 Response Messages

```json
// Success
{
  "type": "ack",
  "intent_action": "move",
  "executed_tick": 45125
}

// Failure
{
  "type": "error",
  "reason": "invalid_position",
  "detail": "Position [50, 55] is blocked"
}
```

---

## 5. Implementation Plan

### 5.1 Phase 1: Minimal Proof of Concept (2-3 weeks)

**Goal:** Agent can move player around town

1. **Add compile flag:** `-DENABLE_GAP`
2. **Create gap_core module:**
   - `Source/gap/gap_core.cpp` - Main coordinator
   - `Source/gap/gap_ipc.cpp` - IPC transport
   - `Source/gap/gap_state.cpp` - State extraction
   - `Source/gap/gap_intent.cpp` - Intent processing

3. **Hook points:**
   ```cpp
   // In game_loop() after tick processing:
   #ifdef ENABLE_GAP
   if (gap_enabled && tick % state_divisor == 0) {
       gap_publish_state(tick);
   }
   #endif
   
   // In game_loop() before player action:
   #ifdef ENABLE_GAP
   if (gap_enabled) {
       gap_process_intents(tick);
   }
   #endif
   ```

4. **Python test agent:**
   - Connect to pipe
   - Read state
   - Move randomly in town
   - Validate movement

### 5.2 Phase 2: Combat Capability (2-3 weeks)

- Add attack/spell intents
- Expand state: monster details, combat status
- Simple kiting behavior demo

### 5.3 Phase 3: Inventory & Items (3-4 weeks)

- Inventory state representation
- Pickup/drop/use intents
- Potion management demo

### 5.4 Phase 4: Polish & Release (2-3 weeks)

- WebSocket transport option
- Rate limiting & safety features
- Documentation & examples
- Basic test suite

---

## 6. Technical Challenges & Solutions

### 6.1 Challenge: Complex Input State Machine

**Issue:** DevilutionX has many UI modes (stores, menus, dialogs) that block normal input

**Solution:** 
- Include `ui_state` in every state message
- Agent checks `can_act` flag before sending intents
- Game validates all intents against current UI state

### 6.2 Challenge: Multiplayer Synchronization

**Issue:** DevilutionX uses deterministic lockstep with delta compression

**Solution (Future):**
- Agent runs on host only initially
- Agent commands treated as host player input
- Investigate running agents on all clients with seed sync

### 6.3 Challenge: State Explosion

**Issue:** Full game state is massive (all items, all monsters, full map)

**Solution:**
- Send only "visible" or "nearby" entities
- Use view radius of 20 tiles
- Add optional detailed state request for specific entities

### 6.4 Challenge: Performance Impact

**Issue:** JSON serialization and IPC overhead

**Solution:**
- State publishing configurable (every N ticks)
- Use message pooling and pre-allocated buffers
- Consider binary protocol (MessagePack) if needed

---

## 7. Safety & Control

- **Kill switch:** F9 key disables GAP instantly
- **Rate limits:** Hard-coded in game, not configurable by agent
- **Validation:** Every intent validated against game rules
- **Local only:** No network access in Phase 1
- **Resource limits:** Max message size, queue depth

---

## 8. Example Agent (Python)

```python
import json
import socket
import struct

class DevilutionXAgent:
    def __init__(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect("/tmp/devilutionx-gap.sock")
        self.tick_rate = None
        
    def read_message(self):
        length_bytes = self.sock.recv(4)
        length = struct.unpack('<I', length_bytes)[0]
        data = self.sock.recv(length)
        return json.loads(data)
    
    def send_message(self, msg):
        data = json.dumps(msg).encode()
        self.sock.send(struct.pack('<I', len(data)) + data)
    
    def run(self):
        # Handshake
        self.send_message({"type": "hello", "version": "0.2.0"})
        hello = self.read_message()
        self.tick_rate = hello["tick_rate"]
        
        # Main loop
        while True:
            msg = self.read_message()
            if msg["type"] == "state":
                self.on_state(msg["data"])
    
    def on_state(self, state):
        # Simple: move toward center of town
        px, py = state["player"]["pos"]
        if px < 48:
            self.send_message({
                "type": "intent",
                "action": "move",
                "params": {"x": px + 1, "y": py}
            })

if __name__ == "__main__":
    agent = DevilutionXAgent()
    agent.run()
```

---

## 9. Success Metrics

Phase 1 is successful if:
- Agent can navigate town without crashes
- Less than 50ms latency per intent
- Under 5% CPU overhead
- Clean integration (< 500 lines of GAP code)

---

## 10. Future Directions

- **Multi-agent:** Multiple AI players in same game
- **Learning:** Record state/action pairs for ML training
- **Modding:** Expose GAP to Lua scripting layer
- **Other games:** Abstract protocol for Doom, OpenTTD, etc.
- **Voice:** Natural language commands → intents

---

## Appendix: DevilutionX Specific Notes

### Coordinate Systems
- Tile coordinates: Used for position (0-112 typical range)
- Pixel coordinates: Not exposed to agents
- Direction: 8-way (N, NE, E, SE, S, SW, W, NW)

### Monster Types (abbreviated in state)
- "SK" = Skeleton
- "ZO" = Zombie  
- "FA" = Fallen One
- (Full mapping in implementation)

### Item Categories (future)
- Simplified to: weapon, armor, potion, scroll, gold, quest
- Full item details available via detailed request

---

*This document represents lessons learned from initial analysis of DevilutionX source. The protocol is intentionally simplified from v0.1 to focus on achievable implementation.*