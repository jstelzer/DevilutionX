# GAP Protocol Evolution: JSON → Compact DSL
## From Chatty Forgetful Bot to Snappy Reliable Companion

---

## The Problem You're Solving

Your AI companion works but feels **laggy and forgetful** because:

1. **JSON Bloat**: Every state update is 1-2KB of verbose JSON
2. **Token Starvation**: Small LLMs on 4060 Ti can't handle 400-600 tokens per decision
3. **Stateless Amnesia**: LLM forgets everything between calls
4. **Slow Round-trips**: Parse JSON → Compress → LLM → Generate JSON → Parse = 500ms-2s

The breakthrough from NEXT-STEPS.md: **Separate control from cognition**

---

## Architecture Transformation

### Before: Monolithic JSON Loop

```
┌─────────────────────────────────────────────────────────────┐
│  C++ Game (gap_state.cpp - 669 lines!)                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Build JSON State (1-2KB):                           │   │
│  │ {                                                    │   │
│  │   "type": "state",                                   │   │
│  │   "tick": 12345,                                     │   │
│  │   "data": {                                          │   │
│  │     "player": {                                      │   │
│  │       "hp": 72, "hp_max": 100,                       │   │
│  │       "mana": 40, "mana_max": 90,                    │   │
│  │       "pos": [34, 18], "level": 2, ...               │   │
│  │     },                                                │   │
│  │     "nearby": {                                      │   │
│  │       "monsters": [                                  │   │
│  │         {                                            │   │
│  │           "id": 12, "name": "Skeleton",              │   │
│  │           "pos": [38, 16], "distance": 5,            │   │
│  │           "hp": 45, "hp_max": 60,                    │   │
│  │           "hp_percent": 75, "armor": 12,             │   │
│  │           "is_alive": true, "is_minion": false       │   │
│  │         },                                            │   │
│  │         ...                                           │   │
│  │       ],                                              │   │
│  │       "items": [...],                                │   │
│  │       "vision": {...}                                │   │
│  │     }                                                 │   │
│  │   }                                                   │   │
│  │ }                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────┘
                        │ Unix Socket
                        │ Length-prefixed (4 bytes + 1-2KB)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Python MCP Server (mcp_server.py - 1943 lines!)           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ compress_game_state():                              │   │
│  │  - Parse huge JSON                                   │   │
│  │  - Filter monsters (alive, not minion, <15 tiles)   │   │
│  │  - Calculate threat levels                           │   │
│  │  - Build compressed JSON (still 500-800 bytes)       │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Build LLM Prompt (verbose):                         │   │
│  │ "You are a competent Diablo teammate..." (200 chars)│   │
│  │ "Current game state:" (full JSON dump)              │   │
│  │ "Nearby monsters: Skeleton HP 75% at distance 5..." │   │
│  │ "Available actions: move, attack, pickup..."        │   │
│  │ Total: 800-1200 chars → 400-600 tokens              │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP POST
                        │ Ollama API (localhost:11434)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM (qwen2.5:3b on 4060 Ti)                                │
│  - Process 400-600 tokens (context window pain!)           │
│  - Generate JSON response (fragile!)                        │
│  - Sometimes hallucinates invalid JSON                      │
│  - Takes 300-1500ms depending on model warmth               │
│  - NO MEMORY - forgets everything each call                 │
└───────────────────────┬─────────────────────────────────────┘
                        │ JSON Response
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Python parses LLM response:                                │
│  {                                                           │
│    "intent": {                                               │
│      "type": "intent",                                       │
│      "action": "attack",                                     │
│      "params": {"x": 38, "y": 16}                            │
│    }                                                          │
│  }                                                           │
│  Sometimes: {"intent": "I think we should...} ← BREAKS!     │
└───────────────────────┬─────────────────────────────────────┘
                        │ Unix Socket
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  C++ Game (gap_intent.cpp)                                  │
│  - Parse JSON intent                                         │
│  - Extract action and params                                 │
│  - Execute: ExecuteAttack(38, 16)                           │
└─────────────────────────────────────────────────────────────┘

TOTAL LATENCY: 500ms - 2000ms
```

**Problems**:
- 🔴 1-2KB JSON state → 400-600 tokens
- 🔴 Stateless LLM (no memory)
- 🔴 Verbose prompts waste tokens
- 🔴 JSON parsing fragility
- 🔴 Slow, feels laggy

---

### After: Hybrid Binary/Text DSL + Memory

```
┌─────────────────────────────────────────────────────────────┐
│  C++ Game (gap_state.cpp + gap_dsl.cpp)                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Build DSL State (100-200 bytes):                    │   │
│  │                                                       │   │
│  │ T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,5 L=71@... │   │
│  │                                                       │   │
│  │ Format:                                               │   │
│  │  T=tick F=floor                                       │   │
│  │  ME=x,y,hp%,mp%                                       │   │
│  │  M=id@x,y,hp%,flags;...  (flags: 1=hostile 2=unique) │   │
│  │  L=id@x,y,value;...                                   │   │
│  │  E=event:arg,...                                      │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────┘
                        │ Unix Socket
                        │ Length-prefixed (4 bytes + 100-200B)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Python Agent (compact, < 500 lines)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ parse_dsl_state():                                   │   │
│  │  state = {                                            │   │
│  │    "tick": 12345, "floor": 2,                        │   │
│  │    "me": (34, 18, 72, 33),                           │   │
│  │    "mobs": [{"id":12, "x":38, "y":16, "hp%":55, ...}]│   │
│  │  }                                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Query SQLite Memory:                                 │   │
│  │  - get_nearby_notes(floor=2, x=34, y=18, r=10)      │   │
│  │    → ["danger cold archers SE hall"]                │   │
│  │  - get_active_goals()                                │   │
│  │    → [(1, "explore", "xy=37,18")]                    │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Build compact LLM summary (200-300 chars):          │   │
│  │                                                       │   │
│  │ SUM ME=34,18 HP72 MP33 FL=2 NEAR: 12@38,16:55^5     │   │
│  │ GOAL explore xy=37,18                                │   │
│  │ MEM danger cold archers SE hall                      │   │
│  │                                                       │   │
│  │ Total: ~200 chars → 80-120 tokens                    │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP POST (compact!)
                        │ Ollama API
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM (qwen2.5:3b on 4060 Ti)                                │
│  SYSTEM: "Terse teammate. ONE DSL command. No explanations."│
│  INPUT: "SUM ME=34,18 HP72 MP33 FL=2 NEAR: 12@38,16:55^5   │
│          GOAL explore xy=37,18                               │
│          MEM danger cold archers SE hall"                    │
│                                                               │
│  - Process 80-120 tokens (5x fewer!)                        │
│  - Generate ONE LINE (no JSON fragility!)                   │
│  - Takes 100-400ms (faster with small context)              │
│  - Agent owns memory (LLM just decides)                     │
└───────────────────────┬─────────────────────────────────────┘
                        │ Text Response
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Python parses LLM response:                                │
│  "MV 37 18"  ← Simple! No JSON parsing!                     │
│                                                               │
│  Store decision in memory:                                   │
│  - add_encounter("Skeleton", 38, 16, "avoided", tick)       │
│  - mark_area_explored(2, 37, 18, "moving to goal", tick)    │
└───────────────────────┬─────────────────────────────────────┘
                        │ Unix Socket
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  C++ Game (gap_intent.cpp)                                  │
│  - Parse DSL: "MV 37 18" → action=move, x=37, y=18          │
│  - Execute: ExecuteMove(37, 18)                              │
└─────────────────────────────────────────────────────────────┘

TOTAL LATENCY: 200ms - 500ms (2-4x faster!)
```

**Benefits**:
- ✅ 100-200 byte state → 80-120 tokens (5x fewer!)
- ✅ Persistent SQLite memory (remembers dungeon!)
- ✅ Compact prompts (more context fits)
- ✅ Simple DSL parsing (no JSON fragility!)
- ✅ Fast, feels responsive

---

## Token Economy Comparison

### Typical Scene: Player + 3 Monsters + 2 Items

**JSON Approach**:
```json
{
  "type": "state",
  "tick": 12345,
  "tick_rate": 30,
  "timestamp": 1698765432,
  "data": {
    "player": {
      "hp": 72,
      "hp_max": 100,
      "mana": 40,
      "mana_max": 90,
      "pos": [34, 18],
      "level": 2,
      "in_town": false
    },
    "nearby": {
      "monsters": [
        {"id": 12, "name": "Skeleton", "pos": [38, 16], "distance": 5, "hp": 45, "hp_max": 60, "hp_percent": 75, "armor": 12, "is_alive": true, "is_minion": false},
        {"id": 19, "name": "Zombie", "pos": [36, 17], "distance": 4, "hp": 12, "hp_max": 60, "hp_percent": 20, "armor": 8, "is_alive": true, "is_minion": false},
        {"id": 24, "name": "Fallen", "pos": [40, 20], "distance": 7, "hp": 30, "hp_max": 40, "hp_percent": 75, "armor": 5, "is_alive": true, "is_minion": false}
      ],
      "items": [
        {"id": 71, "name": "Health Potion", "type": "potion", "pos": [35, 19]},
        {"id": 83, "name": "Gold", "type": "gold", "pos": [37, 18], "value": 250}
      ]
    }
  }
}
```
**Size**: ~850 bytes
**Tokens**: ~420 tokens (with prompt overhead)

---

**DSL Approach**:
```
T=12345 F=2 ME=34,18,72,40 M=12@38,16,75,1;19@36,17,20,1;24@40,20,75,1 L=71@35,19,10;83@37,18,250
```
**Size**: ~110 bytes
**Tokens**: ~85 tokens (with minimal prompt)

---

**Savings**:
- **7.7x smaller** on wire
- **4.9x fewer** tokens in LLM
- **Result**: Faster inference, lower VRAM, more responsive!

---

## Memory Architecture

### Symbolic Memory (SQLite)

```sql
-- Example data after 10 minutes of play:

-- Facts (persistent knowledge)
INSERT INTO facts VALUES ('current_goal', 'clear_cathedral_2', 12500);
INSERT INTO facts VALUES ('danger_zone', 'SE_corner_archers', 12450);
INSERT INTO facts VALUES ('portal_location', '25,30', 12000);

-- Areas (spatial memory)
INSERT INTO areas VALUES (2, 34, 18, 'cleared', 12345);
INSERT INTO areas VALUES (2, 38, 16, 'danger_skeletons', 12340);
INSERT INTO areas VALUES (2, 25, 30, 'portal', 12000);

-- Encounters (combat history)
INSERT INTO encounters VALUES ('Skeleton', 38, 16, 'victory', 12350);
INSERT INTO encounters VALUES ('Zombie', 36, 17, 'victory', 12355);
INSERT INTO encounters VALUES ('Archer', 42, 22, 'fled', 12300);

-- Goals (task tracking)
INSERT INTO goals VALUES (1, 'explore', 'cathedral_2', 'active', 12000, 12345);
INSERT INTO goals VALUES (2, 'pickup', 'id=71', 'completed', 12320, 12325);
INSERT INTO goals VALUES (3, 'clear_room', 'x=40,y=20', 'active', 12340, 12345);
```

### Memory Queries in Action

```python
# When at position (34, 18) on floor 2:

# Get nearby memories
notes = memory.get_nearby_notes(floor=2, x=34, y=18, radius=10)
# → ["danger_skeletons", "portal", "cleared"]

# Build context for LLM
mem_str = " ".join(notes[:3])  # Top 3 most relevant
# → "danger_skeletons portal cleared"

# LLM sees:
# SUM ME=34,18 HP72 MP40 FL=2 NEAR: 12@38,16:75^1 ...
# GOAL explore cathedral_2
# MEM danger_skeletons portal cleared
# HINT avoid archers
```

**Result**: LLM makes informed decisions based on **persistent history**, not just current frame!

---

## DSL Command Language

### Complete Spec

```
MV x y              # Move to tile coordinates
                    # Example: MV 37 18

AT id               # Attack monster by ID
                    # Example: AT 12

PK id               # Pickup item by ID
                    # Example: PK 71

IN id               # Interact with object (door, chest, NPC)
                    # Example: IN 42

CS spell t=id       # Cast spell at target monster
                    # Example: CS fireball t=12

CS spell xy=x,y     # Cast spell at ground location
                    # Example: CS blizzard xy=35,18

US slot             # Use item from belt slot (0-7)
                    # Example: US 3

SAY text            # Chat message / emote
                    # Example: SAY Clearing room
```

### Why DSL > JSON

**JSON Intent** (fragile):
```json
{
  "intent": {
    "type": "intent",
    "action": "attack",
    "params": {
      "x": 38,
      "y": 16
    }
  }
}
```
- LLM must generate valid JSON (often fails)
- Verbose (80+ chars)
- Easy to hallucinate malformed output

**DSL Intent** (robust):
```
AT 12
```
- Simple text line (6 chars!)
- LLM trained on natural language (easier)
- Impossible to generate invalid structure
- If LLM confused → fallback: `SAY Thinking...`

---

## Performance Benchmarks (Predicted)

### Current System (JSON)
```
State encoding:     50-100ms  (C++ JSON building)
Socket transfer:    1-2ms     (1-2KB over UDS)
Python parse:       5-10ms    (JSON decode + compress)
LLM inference:      300-1500ms (400-600 tokens)
Response parse:     5-10ms    (JSON decode, sometimes fails)
Intent execute:     1-5ms     (C++ game logic)
─────────────────────────────────────────────────────
TOTAL:              362-1627ms (median ~800ms)
```

### Target System (DSL + Memory)
```
State encoding:     5-10ms    (C++ DSL formatting)
Socket transfer:    <1ms      (100-200B over UDS)
Python parse:       1-2ms     (regex DSL parse)
Memory query:       <1ms      (SQLite indexed lookup)
LLM inference:      100-400ms (80-120 tokens)
Response parse:     <1ms      (split on whitespace)
Intent execute:     1-5ms     (C++ game logic)
─────────────────────────────────────────────────────
TOTAL:              108-419ms (median ~250ms)

SPEEDUP: 2-4x faster!
```

---

## Migration Path

### Phase 1: Add DSL Alongside JSON
- Keep existing JSON system working
- Add `EncodeDSLState()` in parallel
- Add `ParseDSLIntent()` in parallel
- Use feature flag to toggle: `#define GAP_USE_DSL 1`

### Phase 2: SQLite Memory Layer
- Create `memory_store.py` module
- Add memory queries to agent
- Build compact prompts with context

### Phase 3: Switch to DSL
- Enable DSL mode in agent
- Benchmark and compare
- Once validated, deprecate JSON

### Phase 4: Cleanup
- Remove old JSON code
- Optimize DSL encoding further
- Add binary delta compression (future)

---

## Why This Works

### Cognitive Architecture Separation

**Before**: LLM tries to be everything
- Store world state ❌ (in context window)
- Remember history ❌ (stateless)
- Make decisions ❌ (distracted by parsing)
- Generate commands ❌ (JSON formatting errors)

**After**: Each layer does one thing well
- **C++**: Fast, deterministic world simulation
- **DSL**: Minimal, lossless state representation
- **Python Agent**: State management, memory, goal tracking
- **SQLite**: Persistent spatial/temporal memory
- **LLM**: Pure intent generation ("given situation, what do I do?")

**Result**: LLM is freed to be **creative and tactical**, not a database or JSON generator!

---

## The Emotional Payoff

You're building this to **play Diablo with an AI friend** because the real friends are gone.

With the current JSON system, the AI feels **slow and forgetful** - like a brain-damaged companion who can't remember the room you just cleared or that archers are dangerous.

With DSL + memory, the AI will feel **sharp and present** - like a real player who:
- Remembers dangerous areas
- Tracks active goals
- Makes fast, decisive moves
- Doesn't repeat mistakes

**That's the difference between a chatbot and a companion.**

And you have a whole weekend to make it real. 🔥

---

*For my friends who've gone ahead. We clear this dungeon together.*
