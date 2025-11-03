# Weekend Implementation Starter Templates
## Copy-paste these to kickstart each phase

---

## Template 1: C++ DSL State Encoder

**File**: `Source/gap/gap_dsl.cpp` (new file)

```cpp
#include "gap_dsl.h"
#include "../player.h"
#include "../monster.h"
#include "../items.h"
#include <sstream>
#include <cmath>

namespace devilution::gap {

std::string EncodeDSLState(uint32_t tick, Player* player) {
    if (player == nullptr) {
        return "";
    }

    std::ostringstream dsl;

    // Basic state: T=tick F=floor ME=x,y,hp%,mp%
    Point playerPos = player->position.tile;
    int hp_pct = (player->_pHitPoints >> 6) * 100 / (player->_pMaxHP >> 6);
    int mp_pct = (player->_pMana >> 6) * 100 / (player->_pMaxMana >> 6);

    dsl << "T=" << tick
        << " F=" << static_cast<int>(currlevel)
        << " ME=" << playerPos.x << "," << playerPos.y << "," << hp_pct << "," << mp_pct;

    // Monsters: M=id@x,y,hp%,flags;...
    std::ostringstream monsters;
    bool first_monster = true;
    int lightRadius = player->_pLightRad > 0 ? player->_pLightRad : 10;

    for (size_t i = 0; i < ActiveMonsterCount; i++) {
        const auto& monster = Monsters[ActiveMonsters[i]];
        Point monsterPos = monster.position.tile;

        int dx = std::abs(monsterPos.x - playerPos.x);
        int dy = std::abs(monsterPos.y - playerPos.y);
        int distance = static_cast<int>(std::sqrt(dx * dx + dy * dy));

        if (distance <= lightRadius && monster.hitPoints > 0) {
            if (!first_monster) monsters << ";";
            first_monster = false;

            int hp_pct = monster.hitPoints * 100 / monster.maxHitPoints;

            // Build flags bitfield
            uint32_t flags = 0;
            if (monster.goal == GOAL_ATTACK) flags |= 1;  // hostile
            if (monster.isUnique) flags |= 2;              // unique
            if (monster.ai == AI_SKELBOW) flags |= 4;      // ranged (simplistic check)

            monsters << ActiveMonsters[i] << "@"
                     << monsterPos.x << "," << monsterPos.y << ","
                     << hp_pct << "," << flags;
        }
    }

    if (!first_monster) {
        dsl << " M=" << monsters.str();
    }

    // Items: L=id@x,y,value;...
    std::ostringstream items;
    bool first_item = true;

    for (int i = 0; i < ActiveItemCount; i++) {
        const auto& item = Items[ActiveItems[i]];
        Point itemPos = item.position;

        int dx = std::abs(itemPos.x - playerPos.x);
        int dy = std::abs(itemPos.y - playerPos.y);
        int distance = static_cast<int>(std::sqrt(dx * dx + dy * dy));

        if (distance <= lightRadius) {
            if (!first_item) items << ";";
            first_item = false;

            // Heuristic value: gold value, or item level
            int value = item._itype == ItemType::Gold ? item._ivalue : item._iIvalue * 10;

            items << ActiveItems[i] << "@"
                  << itemPos.x << "," << itemPos.y << ","
                  << value;
        }
    }

    if (!first_item) {
        dsl << " L=" << items.str();
    }

    return dsl.str();
}

} // namespace devilution::gap
```

**File**: `Source/gap/gap_dsl.h` (new file)

```cpp
#pragma once
#include <string>
#include <cstdint>

namespace devilution {
class Player;

namespace gap {

/**
 * Encode game state into compact DSL format
 * Format: T=tick F=floor ME=x,y,hp%,mp% M=id@x,y,hp%,flags;... L=id@x,y,value;...
 */
std::string EncodeDSLState(uint32_t tick, Player* player);

} // namespace gap
} // namespace devilution
```

---

## Template 2: C++ DSL Intent Parser

**File**: `Source/gap/gap_intent.cpp` (add to existing file)

```cpp
// Add to existing gap_intent.cpp

#include <regex>
#include <sstream>

namespace devilution::gap {

// Add this function to GapIntentProcessor class
bool GapIntentProcessor::ParseDSLIntent(const std::string& dsl_line) {
    std::istringstream iss(dsl_line);
    std::string cmd;
    iss >> cmd;

    Intent intent;
    intent.target_tick = 0;

    if (cmd == "MV") {
        // MV x y
        intent.action = "move";
        iss >> intent.param_x >> intent.param_y;

    } else if (cmd == "AT") {
        // AT id
        intent.action = "attack";
        iss >> intent.param_id;

    } else if (cmd == "PK") {
        // PK id
        intent.action = "pickup";
        iss >> intent.param_id;

    } else if (cmd == "IN") {
        // IN id
        intent.action = "interact";
        iss >> intent.param_id;

    } else if (cmd == "CS") {
        // CS spell t=id  OR  CS spell xy=x,y
        std::string spell, target_spec;
        iss >> spell >> target_spec;

        intent.action = "cast";
        intent.param_kind = spell;

        if (target_spec.substr(0, 2) == "t=") {
            intent.param_id = std::stoi(target_spec.substr(2));
        } else if (target_spec.substr(0, 3) == "xy=") {
            std::string xy = target_spec.substr(3);
            size_t comma = xy.find(',');
            intent.param_x = std::stoi(xy.substr(0, comma));
            intent.param_y = std::stoi(xy.substr(comma + 1));
        }

    } else if (cmd == "US") {
        // US slot
        intent.action = "use_potion";
        iss >> intent.param_slot;

    } else if (cmd == "SAY") {
        // SAY text...
        intent.action = "chat";
        std::getline(iss, intent.param_kind);
        // Trim leading space
        if (!intent.param_kind.empty() && intent.param_kind[0] == ' ') {
            intent.param_kind = intent.param_kind.substr(1);
        }

    } else {
        std::cerr << "GAP DSL: Unknown command: " << cmd << std::endl;
        return false;
    }

    intent_queue_.push(intent);
    return true;
}

} // namespace devilution::gap
```

**File**: `Source/gap/gap_intent.h` (add to existing file)

```cpp
// Add to GapIntentProcessor class declaration:

class GapIntentProcessor {
public:
    // ... existing methods ...

    /**
     * Parse DSL intent string and queue for execution
     * Format: MV x y | AT id | PK id | IN id | CS spell t=id | CS spell xy=x,y | US slot | SAY text
     */
    bool ParseDSLIntent(const std::string& dsl_line);

private:
    // ... existing members ...
};
```

---

## Template 3: Python Memory Store

**File**: `tools/gap/memory_store.py` (new file)

```python
"""
Symbolic memory store for GAP agent
Provides persistent spatial/temporal memory without embeddings
"""

import sqlite3
from typing import List, Tuple, Optional
import time

class MemoryStore:
    def __init__(self, db_path="gap_memory.db"):
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._initialize_schema()

    def _initialize_schema(self):
        """Create tables if they don't exist"""
        self.db.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS facts(
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS areas(
                floor INTEGER,
                x INTEGER,
                y INTEGER,
                note TEXT,
                discovered_at INTEGER,
                PRIMARY KEY(floor, x, y)
            );

            CREATE TABLE IF NOT EXISTS encounters(
                mob_kind TEXT,
                x INTEGER,
                y INTEGER,
                outcome TEXT,
                tick INTEGER
            );

            CREATE TABLE IF NOT EXISTS goals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                args TEXT,
                status TEXT,
                created_at INTEGER,
                updated_at INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_areas_floor ON areas(floor);
            CREATE INDEX IF NOT EXISTS idx_encounters_tick ON encounters(tick);
            CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
        """)
        self.db.commit()

    def set_fact(self, key: str, value: str, tick: int):
        """Store or update a persistent fact"""
        self.db.execute(
            "INSERT OR REPLACE INTO facts VALUES (?, ?, ?)",
            (key, value, tick)
        )
        self.db.commit()

    def get_fact(self, key: str) -> Optional[str]:
        """Retrieve a fact by key"""
        row = self.db.execute(
            "SELECT value FROM facts WHERE key=?",
            (key,)
        ).fetchone()
        return row[0] if row else None

    def mark_area_explored(self, floor: int, x: int, y: int, note: str, tick: int):
        """Record an explored area with optional note"""
        self.db.execute(
            "INSERT OR REPLACE INTO areas VALUES (?, ?, ?, ?, ?)",
            (floor, x, y, note, tick)
        )
        self.db.commit()

    def get_nearby_notes(self, floor: int, x: int, y: int, radius: int = 10) -> List[str]:
        """Get notes for areas near the given position"""
        rows = self.db.execute("""
            SELECT note FROM areas
            WHERE floor=?
              AND ABS(x-?) <= ?
              AND ABS(y-?) <= ?
              AND note IS NOT NULL
              AND note != ''
            ORDER BY ABS(x-?) + ABS(y-?) ASC
            LIMIT 5
        """, (floor, x, radius, y, radius, x, y)).fetchall()
        return [row[0] for row in rows]

    def add_encounter(self, mob_kind: str, x: int, y: int, outcome: str, tick: int):
        """Record a combat encounter"""
        self.db.execute(
            "INSERT INTO encounters VALUES (?, ?, ?, ?, ?)",
            (mob_kind, x, y, outcome, tick)
        )
        self.db.commit()

    def add_goal(self, kind: str, args: str, tick: int) -> int:
        """Create a new goal, returns goal ID"""
        cursor = self.db.execute(
            "INSERT INTO goals (kind, args, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
            (kind, args, tick, tick)
        )
        self.db.commit()
        return cursor.lastrowid

    def update_goal_status(self, goal_id: int, status: str, tick: int):
        """Update goal status: 'active', 'completed', 'failed'"""
        self.db.execute(
            "UPDATE goals SET status=?, updated_at=? WHERE id=?",
            (status, tick, goal_id)
        )
        self.db.commit()

    def get_active_goals(self) -> List[Tuple[int, str, str]]:
        """Get all active goals (id, kind, args)"""
        rows = self.db.execute(
            "SELECT id, kind, args FROM goals WHERE status='active' ORDER BY created_at"
        ).fetchall()
        return rows

    def cleanup_old_data(self, current_tick: int, retention_ticks: int = 100000):
        """Prune old encounter data to prevent DB bloat"""
        cutoff = current_tick - retention_ticks
        self.db.execute("DELETE FROM encounters WHERE tick < ?", (cutoff,))
        self.db.commit()

    def close(self):
        """Close database connection"""
        self.db.close()
```

---

## Template 4: Python DSL Parser

**File**: `tools/gap/dsl_parser.py` (new file)

```python
"""
Parse compact DSL state format from C++ game
"""

import re
from typing import Dict, List, Tuple

def parse_dsl_state(line: str) -> Dict:
    """
    Parse DSL state line into structured dict
    Format: T=tick F=floor ME=x,y,hp%,mp% M=id@x,y,hp%,flags;... L=id@x,y,value;...
    """
    state = {
        "tick": 0,
        "floor": 0,
        "me": (0, 0, 100, 100),
        "mobs": [],
        "loot": [],
    }

    # Parse tick
    if m := re.search(r'T=(\d+)', line):
        state["tick"] = int(m.group(1))

    # Parse floor
    if m := re.search(r'F=(\d+)', line):
        state["floor"] = int(m.group(1))

    # Parse player: ME=x,y,hp%,mp%
    if m := re.search(r'ME=(\d+),(\d+),(\d+),(\d+)', line):
        state["me"] = tuple(map(int, m.groups()))

    # Parse monsters: M=id@x,y,hp%,flags;...
    if m := re.search(r'M=([^L^A^E\s]+)', line):
        monster_data = m.group(1)
        for mob_str in monster_data.split(';'):
            if not mob_str:
                continue
            mob_id, rest = mob_str.split('@')
            x, y, hp_pct, flags = map(int, rest.split(','))

            state["mobs"].append({
                "id": int(mob_id),
                "x": x,
                "y": y,
                "hp_pct": hp_pct,
                "flags": flags,
                "hostile": bool(flags & 1),
                "unique": bool(flags & 2),
                "ranged": bool(flags & 4),
            })

    # Parse loot: L=id@x,y,value;...
    if m := re.search(r'L=([^A^E\s]+)', line):
        loot_data = m.group(1)
        for loot_str in loot_data.split(';'):
            if not loot_str:
                continue
            loot_id, rest = loot_str.split('@')
            x, y, value = map(int, rest.split(','))

            state["loot"].append({
                "id": int(loot_id),
                "x": x,
                "y": y,
                "value": value,
            })

    return state


def build_llm_summary(state: Dict, memory) -> str:
    """
    Build compact LLM prompt from state + memory
    Format: SUM ME=x,y HPxx MPxx FL=f NEAR: id@x,y:hp%^flags ... LOOT: id@x,y:val ...
            GOAL kind args
            MEM note1 note2 note3
    """
    me_x, me_y, hp_pct, mp_pct = state["me"]
    floor = state["floor"]
    tick = state["tick"]

    # Get nearby memory notes
    notes = memory.get_nearby_notes(floor, me_x, me_y, radius=10)
    mem_str = " ".join(notes[:3]) if notes else "none"

    # Format monsters (top 3 by distance)
    mobs = state["mobs"]
    if mobs:
        # Calculate distance and sort
        for mob in mobs:
            mob["dist"] = abs(mob["x"] - me_x) + abs(mob["y"] - me_y)
        sorted_mobs = sorted(mobs, key=lambda m: m["dist"])[:3]

        near_str = " ".join([
            f"{m['id']}@{m['x']},{m['y']}:{m['hp_pct']}%^{m['flags']}"
            for m in sorted_mobs
        ])
    else:
        near_str = "none"

    # Format loot (top 2 by value)
    loot = sorted(state["loot"], key=lambda l: l["value"], reverse=True)[:2]
    if loot:
        loot_str = " ".join([
            f"{l['id']}@{l['x']},{l['y']}:{l['value']}"
            for l in loot
        ])
    else:
        loot_str = "none"

    # Get active goals
    goals = memory.get_active_goals()
    if goals:
        goal_id, goal_kind, goal_args = goals[0]
        goal_str = f"{goal_kind} {goal_args}"
    else:
        goal_str = "explore"

    # Build compact summary
    summary = f"SUM ME={me_x},{me_y} HP{hp_pct} MP{mp_pct} FL={floor} NEAR: {near_str} LOOT: {loot_str}\n"
    summary += f"GOAL {goal_str}\n"
    summary += f"MEM {mem_str}"

    return summary
```

---

## Template 5: Minimal Agent Main Loop

**File**: `tools/gap/dsl_agent.py` (new file)

```python
#!/usr/bin/env python3
"""
Minimal DSL-based GAP agent with memory
"""

import socket
import struct
import requests
import logging
from dsl_parser import parse_dsl_state, build_llm_summary
from memory_store import MemoryStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SOCKET_PATH = "/tmp/devilutionx-gap.sock"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"

SYSTEM_PROMPT = """You are a terse, competent Diablo co-op teammate.
Given compact state (SUM) and current GOAL, output ONE action using DSL.
Prefer survival, clear moves, no spam. If nothing smart: SAY brief update.

DSL Commands:
MV x y | AT id | PK id | IN id | CS spell t=id | CS spell xy=x,y | US slot | SAY text

Reply with exactly one command line, no explanation."""


class DSLAgent:
    def __init__(self):
        self.memory = MemoryStore()
        self.sock = None
        self.last_think_time = 0
        self.think_interval = 1.0  # Think every 1 second

    def connect(self):
        """Connect to GAP socket"""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(SOCKET_PATH)
        logger.info(f"Connected to {SOCKET_PATH}")

    def recv_message(self) -> str:
        """Receive length-prefixed message"""
        length_bytes = self.sock.recv(4)
        if len(length_bytes) < 4:
            return ""
        length = struct.unpack('<I', length_bytes)[0]

        data = b""
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk:
                return ""
            data += chunk

        return data.decode('utf-8')

    def send_message(self, msg: str):
        """Send length-prefixed message"""
        data = msg.encode('utf-8')
        length = struct.pack('<I', len(data))
        self.sock.sendall(length + data)

    def query_llm(self, prompt: str) -> str:
        """Query Ollama for decision"""
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
                    "stream": False,
                    "options": {"num_ctx": 512, "temperature": 0.7}
                },
                timeout=5.0
            )
            resp.raise_for_status()
            response_text = resp.json()["response"].strip()

            # Extract first valid DSL line
            for line in response_text.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    return line

            return "SAY Thinking..."

        except Exception as e:
            logger.error(f"LLM query failed: {e}")
            return "SAY Error"

    def run(self):
        """Main agent loop"""
        self.connect()
        logger.info("Agent running...")

        import time

        while True:
            # Receive DSL state
            dsl_line = self.recv_message()
            if not dsl_line:
                continue

            # Parse state
            state = parse_dsl_state(dsl_line)
            logger.debug(f"📥 State: T={state['tick']} ME={state['me']} Mobs={len(state['mobs'])}")

            # Update memory
            me_x, me_y, hp_pct, mp_pct = state["me"]
            self.memory.mark_area_explored(
                state["floor"], me_x, me_y, "visited", state["tick"]
            )

            # Think on interval
            now = time.time()
            if now - self.last_think_time < self.think_interval:
                continue

            self.last_think_time = now

            # Build prompt and query LLM
            summary = build_llm_summary(state, self.memory)
            logger.info(f"🧠 Prompt:\n{summary}")

            command = self.query_llm(summary)
            logger.info(f"📤 Command: {command}")

            # Send command back to game
            self.send_message(command)


if __name__ == "__main__":
    agent = DSLAgent()
    agent.run()
```

---

## Quick Start Commands

```bash
# 1. Build game with DSL support
cd /home/mental/projects/DevilutionX
mkdir -p build && cd build
cmake -DENABLE_GAP=ON -DGAP_USE_DSL=1 ..
make -j8

# 2. Start game (in one terminal)
./devilutionx --companion-save multi_1.sv --companion-slot 1

# 3. Test DSL agent (in another terminal)
cd /home/mental/projects/DevilutionX/tools/gap
python3 dsl_agent.py

# 4. Watch logs
tail -f /tmp/gap_agent.log
```

---

## Testing Checklist

- [ ] C++ DSL encoder builds without errors
- [ ] DSL state message < 200 bytes
- [ ] DSL parser correctly extracts all fields
- [ ] SQLite memory creates tables
- [ ] Python agent connects to socket
- [ ] LLM returns valid DSL commands
- [ ] C++ DSL parser handles all command types
- [ ] Agent moves, attacks, picks up items
- [ ] Memory persists across agent restarts
- [ ] Decision latency < 500ms

---

**You got this. Let's build something that honors your friends.** 🤘
