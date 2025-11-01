"""
Parse compact DSL state format from C++ game

Converts compact binary/text format to structured Python dict:
    T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1;19@36,17,20,1
    →
    {"tick": 12345, "floor": 2, "me": (34,18,72,33), "mobs": [...], ...}
"""

import re
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


def parse_dsl_state(line: str) -> Dict:
    """
    Parse DSL state line into structured dict

    Format: T=tick F=floor ME=x,y,hp%,mp% M=id@x,y,hp%,flags;... L=id@x,y,value;...

    Example:
        T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1 L=71@35,19,10
        →
        {
            "tick": 12345,
            "floor": 2,
            "me": (34, 18, 72, 33),
            "mobs": [{"id": 12, "x": 38, "y": 16, "hp_pct": 55, "flags": 1, ...}],
            "loot": [{"id": 71, "x": 35, "y": 19, "value": 10}]
        }
    """
    state = {
        "tick": 0,
        "floor": 0,
        "me": (0, 0, 100, 100),
        "player": None,  # Main player position (x, y) if companion
        "mobs": [],
        "loot": [],
    }

    if not line or not line.strip():
        return state

    try:
        # Parse tick: T=12345
        if m := re.search(r'T=(\d+)', line):
            state["tick"] = int(m.group(1))

        # Parse floor: F=2
        if m := re.search(r'F=(\d+)', line):
            state["floor"] = int(m.group(1))

        # Parse player: ME=x,y,hp%,mp%
        if m := re.search(r'ME=(\d+),(\d+),(\d+),(\d+)', line):
            state["me"] = tuple(map(int, m.groups()))

        # Parse main player position: PLYR=x,y
        if m := re.search(r'PLYR=(\d+),(\d+)', line):
            state["player"] = tuple(map(int, m.groups()))

        # Parse monsters: M=id@x,y,hp%,flags;...
        # Use negative lookbehind to avoid matching L= or E=
        if m := re.search(r'M=([^LE\s]+)', line):
            monster_data = m.group(1)
            for mob_str in monster_data.split(';'):
                if not mob_str:
                    continue

                try:
                    mob_id, rest = mob_str.split('@')
                    x, y, hp_pct, flags = map(int, rest.split(','))

                    # Decode flags
                    hostile = bool(flags & 1)
                    unique = bool(flags & 2)
                    ranged = bool(flags & 4)

                    # Calculate distance from player
                    me_x, me_y, _, _ = state["me"]
                    dist = abs(x - me_x) + abs(y - me_y)  # Manhattan distance

                    state["mobs"].append({
                        "id": int(mob_id),
                        "x": x,
                        "y": y,
                        "hp_pct": hp_pct,
                        "flags": flags,
                        "hostile": hostile,
                        "unique": unique,
                        "ranged": ranged,
                        "dist": dist,
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse monster: {mob_str} - {e}")
                    continue

        # Parse loot: L=id@x,y,value;...
        if m := re.search(r'L=([^AE\s]+)', line):
            loot_data = m.group(1)
            for loot_str in loot_data.split(';'):
                if not loot_str:
                    continue

                try:
                    loot_id, rest = loot_str.split('@')
                    x, y, value = map(int, rest.split(','))

                    # Calculate distance
                    me_x, me_y, _, _ = state["me"]
                    dist = abs(x - me_x) + abs(y - me_y)

                    state["loot"].append({
                        "id": int(loot_id),
                        "x": x,
                        "y": y,
                        "value": value,
                        "dist": dist,
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse loot: {loot_str} - {e}")
                    continue

        # Could add E= (events) parsing here in future

    except Exception as e:
        logger.error(f"Failed to parse DSL state: {line[:100]}... - {e}")
        return state

    return state


def build_llm_summary(state: Dict, memory, recent_chat=None) -> str:
    """
    Build compact LLM prompt from state + memory + chat

    Format:
        SUM ME=x,y HP<hp%> MP<mp%> FL=<floor> NEAR: <monsters> LOOT: <loot>
        CHAT <sender>: <message>
        GOAL <kind> <args>
        MEM <note1> <note2> <note3>

    Example:
        SUM ME=34,18 HP72 MP33 FL=2 NEAR: 12@38,16:55^1 19@36,17:20^1 LOOT: 71@35,19:10
        CHAT player: can you hear me?
        GOAL explore cathedral_2
        MEM danger_skeletons portal cleared
    """
    recent_chat = recent_chat or []
    me_x, me_y, hp_pct, mp_pct = state["me"]
    floor = state["floor"]

    # Get nearby memory notes
    notes = memory.get_nearby_notes(floor, me_x, me_y, radius=10)
    mem_str = " ".join(notes[:3]) if notes else "none"

    # Format monsters (top 3 by distance)
    mobs = state["mobs"]
    if mobs:
        # Sort by distance
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
        # Default exploration goal if none set
        goal_str = "explore"

    # Calculate distance to main player
    player_info = ""
    safe_tile = ""
    if state.get("player"):
        plyr_x, plyr_y = state["player"]
        dist = abs(plyr_x - me_x) + abs(plyr_y - me_y)
        player_info = f" PLYR={plyr_x},{plyr_y} dist={dist}"
        # Player position is the safe tile
        safe_tile = f" SAFE_TILE={plyr_x},{plyr_y}"

    # Calculate risk level
    risk = "low"
    if hp_pct < 30:
        risk = "high"
    elif hp_pct < 50 or len(mobs) > 3:
        risk = "med"

    # Best loot hint
    best_loot = ""
    if loot and loot[0]["value"] > 100:
        best = loot[0]
        best_loot = f" BEST_LOOT={best['id']}@{best['x']},{best['y']}:{best['value']}"

    # Build compact summary with risk signals
    summary = f"SUM ME={me_x},{me_y} HP{hp_pct} MP{mp_pct} FL={floor}{player_info} NEAR: {near_str} LOOT: {loot_str}\n"
    summary += f"RISK={risk}{safe_tile}{best_loot}\n"

    # Add recent chat messages
    if recent_chat:
        for sender, message in recent_chat[-3:]:  # Last 3 messages
            summary += f"CHAT {sender}: {message}\n"

    summary += f"GOAL {goal_str}\n"
    summary += f"MEM {mem_str}"

    return summary


if __name__ == "__main__":
    # Test DSL parser
    logging.basicConfig(level=logging.INFO)

    test_state = "T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1;19@36,17,20,1 L=71@35,19,10;83@37,18,250"

    print(f"Input: {test_state}\n")

    parsed = parse_dsl_state(test_state)
    print(f"Parsed state:")
    print(f"  Tick: {parsed['tick']}")
    print(f"  Floor: {parsed['floor']}")
    print(f"  Me: x={parsed['me'][0]}, y={parsed['me'][1]}, hp={parsed['me'][2]}%, mp={parsed['me'][3]}%")
    print(f"  Monsters: {len(parsed['mobs'])}")
    for mob in parsed['mobs']:
        print(f"    #{mob['id']} at ({mob['x']},{mob['y']}) HP={mob['hp_pct']}% dist={mob['dist']} hostile={mob['hostile']}")
    print(f"  Loot: {len(parsed['loot'])}")
    for item in parsed['loot']:
        print(f"    #{item['id']} at ({item['x']},{item['y']}) value={item['value']} dist={item['dist']}")

    # Test LLM summary (mock memory)
    class MockMemory:
        def get_nearby_notes(self, *args, **kwargs):
            return ["cleared", "danger_archers"]
        def get_active_goals(self):
            return [(1, "explore", "cathedral_2")]

    summary = build_llm_summary(parsed, MockMemory())
    print(f"\nLLM Summary ({len(summary)} chars):")
    print(summary)

    print("\n✅ DSL parser test complete!")
