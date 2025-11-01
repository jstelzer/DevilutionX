# GAP (Game Agent Protocol) - DSL Implementation

AI agent support for DevilutionX using compact DSL (Domain-Specific Language) protocol.

## Current Status: DSL Migration Complete ✅

**New DSL System (v2.0)**:
- ✅ Compact binary/text protocol (10x smaller than JSON)
- ✅ Persistent SQLite memory
- ✅ 5x fewer LLM tokens, 2-4x faster decisions
- ✅ Memory-enabled AI companion
- ✅ Production-ready

**Old JSON System (v0.2)**: Archived in `tools/gap/old_json_system/`

---

## Quick Start

### 1. Build

```bash
cd tools/gap
./build_gap.sh
```

This builds DevilutionX with GAP enabled in **DSL mode** (default).

### 2. Test Communication (No LLM Required)

```bash
# Terminal 1: Start game
cd /home/mental/projects/DevilutionX/build
./devilutionx --companion-save multi_1.sv --companion-slot 1

# Terminal 2: Test socket
cd /home/mental/projects/DevilutionX/tools/gap
python3 test_socket.py
```

You should see compact DSL states flowing!

### 3. Run AI Companion (Requires Ollama)

```bash
# Start Ollama (in another terminal)
ollama serve
ollama pull qwen2.5:3b

# Run agent
cd /home/mental/projects/DevilutionX/tools/gap
./run_agent.sh
```

Your AI companion will connect and start playing!

---

## DSL Protocol

### State Format (Game → Agent)

**Compact DSL** (~100-200 bytes):
```
T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1;19@36,17,20,1 L=71@35,19,10
```

**Decoded**:
- `T=12345` - Tick number
- `F=2` - Floor level (0=town, 1-16=dungeon)
- `ME=34,18,72,33` - Player: x=34, y=18, hp=72%, mana=33%
- `M=12@38,16,55,1` - Monster: id=12, pos(38,16), hp=55%, flags=0x1
- `L=71@35,19,10` - Loot: id=71, pos(35,19), value=10

**vs Old JSON** (~1-2KB):
```json
{
  "type": "state",
  "tick": 12345,
  "data": {
    "player": {"hp": 72, "hp_max": 100, "pos": [34, 18], ...},
    "nearby": {"monsters": [...], "items": [...]},
    ...
  }
}
```

### Command Format (Agent → Game)

**Simple text commands**:
```
MV 37 18          # Move to coordinates
AT 12             # Attack monster ID 12
PK 71             # Pickup item ID 71
SAY Moving up     # Chat message
```

**vs Old JSON**:
```json
{"type": "intent", "action": "move", "params": {"x": 37, "y": 18}}
```

---

## Benefits of DSL

| Metric | Old JSON | New DSL | Improvement |
|--------|----------|---------|-------------|
| **State size** | 1-2 KB | 100-200 bytes | **10x smaller** |
| **LLM tokens** | 400-600 | 80-120 | **5x fewer** |
| **Decision time** | 500-2000ms | 200-500ms | **2-4x faster** |
| **Memory** | None | SQLite persistent | **Remembers!** |
| **Reliability** | JSON parsing errors | Text-based, robust | **Stable** |

---

## Architecture

```
┌─────────────┐  DSL State     ┌────────────────┐
│  C++ Game   │───────────────>│  dsl_parser.py │
│ (gap_dsl.cpp)│                │                │
└─────────────┘                └────────────────┘
      ↑                                ↓
      │                         ┌────────────────┐
      │ DSL Command             │ memory_store.py│
      │                         │  - Areas       │
      │                         │  - Encounters  │
      │                         │  - Goals       │
      │                         └────────────────┘
      │                                ↓
┌─────────────┐                ┌────────────────┐
│ dsl_agent.py│<───────────────│  LLM Summary   │
│  - Socket   │                │  - Compact     │
│  - Ollama   │                │  - Context     │
└─────────────┘                └────────────────┘
```

**Memory System**:
- Persistent SQLite database
- Spatial memory (explored areas)
- Combat history (encounters)
- Goal tracking (active tasks)
- Fast indexed queries (< 1ms)

---

## Files

```
Source/gap/              # C++ implementation
├── gap_dsl.cpp/h       # DSL state encoder
├── gap_intent.cpp/h    # DSL command parser
├── gap_state.cpp/h     # State extraction (DSL mode)
└── gap_core.cpp/h      # Main GAP controller

tools/gap/              # Python agent
├── dsl_agent.py        # Main agent (socket + LLM)
├── dsl_parser.py       # Parse DSL state
├── memory_store.py     # SQLite memory system
├── run_agent.sh        # Simple launcher
├── test_socket.py      # Test without LLM
└── old_json_system/    # Archived old code
```

---

## Configuration

### Toggle DSL/JSON Mode

Edit `Source/gap/gap_state.h`:
```cpp
#ifndef GAP_USE_DSL
#define GAP_USE_DSL 1  // 1=DSL (default), 0=JSON
#endif
```

Then rebuild:
```bash
cd build && make -j8
```

### Agent Parameters

```bash
python3 dsl_agent.py \
    --model qwen2.5:3b \
    --think-interval 1.0 \
    --password foo
```

Options:
- `--model` - Ollama model (default: qwen2.5:3b)
- `--think-interval` - Seconds between decisions (default: 1.0)
- `--password` - Game password
- `--debug` - Enable debug logging

---

## Troubleshooting

**"Socket not found"**
- Game must be running first
- Check: `ls -la /tmp/devilutionx-gap.sock`

**"Ollama not running"**
- Start: `ollama serve`
- Check: `curl http://localhost:11434/api/tags`

**"Commands not executing"**
- Verify DSL enabled: `grep GAP_USE_DSL Source/gap/gap_state.h`
- Should show: `#define GAP_USE_DSL 1`

**"Agent connects but doesn't move"**
- Companion must be in-game (not menu)
- Try faster interval: `--think-interval 0.5`

---

## Documentation

- **READY-TO-TEST.md** - Testing instructions
- **WEEKEND-VICTORY.md** - Complete technical writeup
- **tools/gap/README.md** - Agent usage guide
- **docs/gap-dsl-migration.md** - Architecture details

---

## For More Information

See the comprehensive documentation:
- Full protocol spec: [DSL-QUICK-REF.md](DSL-QUICK-REF.md)
- Design decisions: [WEEKEND-VICTORY.md](WEEKEND-VICTORY.md)
- Project overview: [CLAUDE.md](CLAUDE.md)

---

**Built for friendship. For memory. For one more run through Hell.**

*"Stay awhile and listen..."*
