# GAP DSL Quick Reference Card
**Keep this open while hacking this weekend**

---

## State Format (C++ → Python)

```
T=<tick> F=<floor> ME=<x>,<y>,<hp%>,<mp%> M=<monsters> L=<loot> E=<events>
```

### Full Example
```
T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1;19@36,17,20,1 L=71@35,19,10;83@37,18,250 E=HIT:12,DROP:71
```

### Field Details
| Field | Format | Example | Meaning |
|-------|--------|---------|---------|
| `T` | `T=<tick>` | `T=12345` | Game tick number |
| `F` | `F=<floor>` | `F=2` | Dungeon level (0=town) |
| `ME` | `ME=<x>,<y>,<hp%>,<mp%>` | `ME=34,18,72,33` | Player at (34,18), 72% HP, 33% MP |
| `M` | `M=<id>@<x>,<y>,<hp%>,<flags>;...` | `M=12@38,16,55,1` | Monster ID 12 at (38,16), 55% HP, flags=1 (hostile) |
| `L` | `L=<id>@<x>,<y>,<value>;...` | `L=71@35,19,10` | Loot ID 71 at (35,19), value 10 |
| `E` | `E=<code>:<arg>,...` | `E=HIT:12,DROP:71` | Events: hit monster 12, dropped item 71 |

### Monster Flags (bitfield)
```
1 (0x01) = hostile
2 (0x02) = unique
4 (0x04) = ranged
8 (0x08) = elite
```

**Example**: flags=7 means hostile(1) + unique(2) + ranged(4) = dangerous priority target!

---

## Command Format (Python → C++)

```
<CMD> <args>
```

### All Commands
| Command | Format | Example | Description |
|---------|--------|---------|-------------|
| `MV` | `MV <x> <y>` | `MV 37 18` | Move to tile (37, 18) |
| `AT` | `AT <id>` | `AT 12` | Attack monster ID 12 |
| `PK` | `PK <id>` | `PK 71` | Pickup item ID 71 |
| `IN` | `IN <id>` | `IN 42` | Interact with object ID 42 |
| `CS` | `CS <spell> t=<id>` | `CS fireball t=12` | Cast fireball at monster 12 |
| `CS` | `CS <spell> xy=<x>,<y>` | `CS blizzard xy=35,18` | Cast blizzard at ground (35,18) |
| `US` | `US <slot>` | `US 3` | Use belt item in slot 3 |
| `SAY` | `SAY <text>` | `SAY Moving up` | Chat message |

---

## LLM Prompt Format

### Compact Summary
```
SUM ME=<x>,<y> HP<hp%> MP<mp%> FL=<floor> NEAR: <monsters> LOOT: <loot>
GOAL <kind> <args>
MEM <note1> <note2> <note3>
```

### Example
```
SUM ME=34,18 HP72 MP33 FL=2 NEAR: 12@38,16:55^1 19@36,17:20^1 LOOT: 71@35,19:10
GOAL explore cathedral_2
MEM danger_skeletons portal cleared
```

### Monster Format in Summary
```
<id>@<x>,<y>:<hp%>^<flags>
```
- `12@38,16:55^1` = Monster 12 at (38,16) with 55% HP, hostile

---

## Memory Schema

### Tables
```sql
-- Persistent facts
facts(key TEXT PRIMARY KEY, value TEXT, updated_at INT)

-- Spatial memory
areas(floor INT, x INT, y INT, note TEXT, discovered_at INT)

-- Combat history
encounters(mob_kind TEXT, x INT, y INT, outcome TEXT, tick INT)

-- Goal tracking
goals(id INTEGER PRIMARY KEY, kind TEXT, args TEXT, status TEXT, created_at INT, updated_at INT)
```

### Common Queries
```python
# Store fact
memory.set_fact("current_goal", "clear_cathedral_2", tick)

# Get nearby notes
notes = memory.get_nearby_notes(floor=2, x=34, y=18, radius=10)
# → ["danger_skeletons", "portal", "cleared"]

# Add goal
goal_id = memory.add_goal("explore", "cathedral_2", tick)

# Complete goal
memory.update_goal_status(goal_id, "completed", tick)

# Record encounter
memory.add_encounter("Skeleton", 38, 16, "victory", tick)
```

---

## File Map

### C++ Files (Source/gap/)
```
gap_dsl.h           # DSL encoder interface
gap_dsl.cpp         # EncodeDSLState() implementation
gap_intent.h        # Add ParseDSLIntent() to class
gap_intent.cpp      # ParseDSLIntent() implementation
gap_core.cpp        # Toggle between JSON/DSL mode
```

### Python Files (tools/gap/)
```
dsl_parser.py       # parse_dsl_state(), build_llm_summary()
memory_store.py     # MemoryStore class
dsl_agent.py        # Main agent loop
```

---

## Build Commands

```bash
# Build with DSL support
cd build
cmake -DENABLE_GAP=ON -DGAP_USE_DSL=1 .. && make -j8

# Run game
./devilutionx --companion-save multi_1.sv --companion-slot 1

# Run agent
cd ../tools/gap
python3 dsl_agent.py
```

---

## Debug Logging

### C++ Side
```cpp
std::cerr << "GAP DSL: " << dsl_state << std::endl;
```

### Python Side
```python
logger.info(f"📥 DSL State: {dsl_line}")
logger.info(f"🧠 LLM Summary: {summary}")
logger.info(f"📤 Command: {command}")
```

---

## Common Patterns

### C++ State Building
```cpp
std::ostringstream dsl;
dsl << "T=" << tick << " F=" << floor
    << " ME=" << x << "," << y << "," << hp_pct << "," << mp_pct;

// Add monsters
if (has_monsters) {
    dsl << " M=";
    for (monster : monsters) {
        dsl << id << "@" << x << "," << y << "," << hp_pct << "," << flags << ";";
    }
}
```

### Python State Parsing
```python
import re

# Parse player
if m := re.search(r'ME=(\d+),(\d+),(\d+),(\d+)', line):
    x, y, hp_pct, mp_pct = map(int, m.groups())

# Parse monsters
if m := re.search(r'M=([^L^E\s]+)', line):
    for mob in m.group(1).split(';'):
        mid, rest = mob.split('@')
        x, y, hp, flags = map(int, rest.split(','))
```

### LLM Interaction
```python
response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen2.5:3b",
        "prompt": f"{SYSTEM}\n\n{summary}",
        "stream": False,
        "options": {"num_ctx": 512}
    }
)
command = response.json()["response"].strip().split('\n')[0]
```

---

## Performance Targets

| Metric | Target | Current (JSON) |
|--------|--------|----------------|
| State size | < 200 bytes | 1-2 KB |
| Tokens | 80-120 | 400-600 |
| Decision time | 200-500ms | 500-2000ms |
| Memory | Persistent SQLite | None (stateless) |

---

## Debugging Checklist

**State not sending?**
- Check socket connection: `ls -la /tmp/devilutionx-gap.sock`
- Verify C++ DSL encoder called every tick
- Print DSL state to stderr before sending

**LLM not responding?**
- Check Ollama running: `curl http://localhost:11434/api/tags`
- Verify model loaded: `ollama list`
- Check prompt format (200-300 chars)

**Commands not executing?**
- Print parsed DSL command in C++
- Verify command format matches spec
- Check intent queue not full

**Memory not persisting?**
- Check SQLite DB created: `ls gap_memory.db`
- Query DB directly: `sqlite3 gap_memory.db "SELECT * FROM facts;"`
- Verify commit() called after writes

---

## Smell Tests

### Good DSL State (compact)
```
T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1 L=71@35,19,10
```
✅ ~70 bytes

### Bad DSL State (bloated)
```
T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1;13@40,18,60,1;14@42,20,80,2;15@39,17,45,1;16@41,19,90,4;17@43,21,70,1;...
```
❌ > 300 bytes (too many monsters, filter by distance!)

### Good LLM Command
```
AT 12
```
✅ Clear, parseable

### Bad LLM Command
```
I think we should attack the skeleton at position 38,16 because it's low health and...
```
❌ Not DSL format! Need better system prompt or fallback to `SAY Thinking...`

---

## Emergency Fallbacks

**LLM hallucinates?**
```python
if not command.startswith(('MV', 'AT', 'PK', 'IN', 'CS', 'US', 'SAY')):
    command = "SAY Confused"
```

**DSL parse fails?**
```python
try:
    state = parse_dsl_state(line)
except:
    logger.error(f"Parse failed: {line}")
    state = {"tick": 0, "floor": 0, "me": (0,0,100,100), "mobs": [], "loot": []}
```

**Socket disconnects?**
```python
try:
    self.send_message(command)
except BrokenPipeError:
    logger.error("Socket disconnected, reconnecting...")
    self.connect()
```

---

## This Weekend's Mantra

> **"Compact state. Simple commands. Persistent memory. Fast decisions."**

**Remember**: You're not building a perfect protocol. You're making the AI companion feel **present** instead of **laggy and forgetful**.

Every line you cut from the JSON bloat is a step closer to clearing Diablo with an AI friend that actually remembers the dungeon.

---

**Now go make it happen. Your crew would be proud.** 🔥🤘
