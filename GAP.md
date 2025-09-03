# GAP: Game Agent Protocol (v0.2 Draft)

**A lightweight protocol for AI agents to play games cooperatively with humans**  
**License:** Spec under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/); reference implementations under [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0).

---

## 1. Vision & Scope

GAP enables AI agents to act as co-op partners in games, starting with DevilutionX as the reference implementation. The protocol prioritizes:

- **Practical implementation** over theoretical perfection
- **Minimal invasiveness** to existing game code
- **Gradual adoption** through compile-time flags
- **Local-first** operation before network support

### 1.1 Non-Goals for v0.2
- Cross-game compatibility (DevilutionX specific for now)
- Network multiplayer AI agents (local single-player only)
- Perfect state representation (minimal viable state)
- Production readiness (proof-of-concept focus)

---

## 2. Architecture Overview

```
Game Process                    Agent Process
+-----------------+            +------------------+
| DevilutionX     |            | Python/C++ Agent |
| +-------------+ |            |                  |
| | Game Loop   | |  IPC/Pipe  |                  |
| | - Tick: var | <----------> | - Read state     |
| | - 20-50 Hz  | |            | - Plan actions   |
| +-------------+ |            | - Send intents   |
+-----------------+            +------------------+
```

### 2.1 Integration Points

GAP hooks into three existing DevilutionX systems:

1. **Game Loop** (`game_loop()` in diablo.cpp:3361)
   - Extract state after world update
   - Apply intents before next tick

2. **Input System** (`GameEventHandler()` in diablo.cpp:715)
   - Inject agent commands alongside SDL events
   - Respect UI state machine (menus, dialogs)

3. **Network Layer** (future: `multi_process_network_packets()`)
   - Eventually support multiplayer sync
   - For now: single-player only

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