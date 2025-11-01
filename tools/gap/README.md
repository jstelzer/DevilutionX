# GAP DSL Agent

**Compact, memory-enabled AI companion for DevilutionX**

This is the new DSL-based agent that replaces the verbose JSON system with:
- 10x smaller messages (100-200 bytes vs 1-2KB)
- 5x fewer tokens (80-120 vs 400-600)
- 2-4x faster decisions (200-500ms vs 500-2000ms)
- Persistent SQLite memory

## Quick Start

### 1. Build Game with DSL Enabled

```bash
cd build
cmake -DENABLE_GAP=ON -DGAP_USE_DSL=1 ..
make -j8
```

### 2. Start Game

```bash
./devilutionx --companion-save multi_1.sv --companion-slot 1
```

### 3. Run Agent

```bash
cd tools/gap
python3 dsl_agent.py --model qwen2.5:3b --password foo
```

That's it! Your AI companion will connect and start playing.

## Files

- **dsl_agent.py** - Main agent (socket + LLM loop)
- **dsl_parser.py** - Parse compact DSL state from C++
- **memory_store.py** - Persistent SQLite memory
- **run_agent.sh** - Simple launcher script

## DSL Protocol

### State Format (C++ → Python)
```
T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1;19@36,17,20,1 L=71@35,19,10
```

### Command Format (Python → C++)
```
MV 37 18          # Move
AT 12             # Attack monster
PK 71             # Pickup item
SAY Moving up     # Chat
```

## Configuration

Edit `dsl_agent.py` or pass CLI args:
- `--socket` - GAP socket path (default: /tmp/devilutionx-gap.sock)
- `--model` - Ollama model (default: qwen2.5:3b)
- `--password` - Game password
- `--think-interval` - Seconds between LLM calls (default: 1.0)

## Memory

The agent remembers:
- Explored areas (floor, coordinates, notes)
- Combat encounters (victories, deaths)
- Dangerous zones (where you died)
- Active goals (explore, clear room, etc.)

Memory persists in `gap_memory.db` - delete to reset.

## Old JSON System

The old mcp_server.py and related files are in `old_json_system/` for reference.

## Troubleshooting

**Agent won't connect?**
- Check socket exists: `ls -la /tmp/devilutionx-gap.sock`
- Game must be running first

**LLM not responding?**
- Verify Ollama running: `ollama list`
- Check model loaded: `ollama pull qwen2.5:3b`

**Commands not executing?**
- Check game built with `-DGAP_USE_DSL=1`
- Look for "GAP DSL:" messages in game stderr

## Development

Run tests:
```bash
python3 memory_store.py  # Test memory
python3 dsl_parser.py    # Test parser (when created)
```

## For My Friends

This project is dedicated to the friends who played Diablo with me and have since passed on. This AI companion keeps their memory alive in the dungeons we once cleared together.

*"Stay awhile and listen..."*
