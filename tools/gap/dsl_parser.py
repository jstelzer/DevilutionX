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

    Format: T=tick F=floor ME=x,y,hp%,mp% M=id@x,y,hp%,flags;... L=id@x,y,value,type,qual;... B=type,type,...

    Example:
        T=12345 F=2 ME=34,18,72,33 M=12@38,16,55,1 L=71@35,19,150,sw,m B=hp,mp,em,em,hp,hp,rj,em
        →
        {
            "tick": 12345,
            "floor": 2,
            "me": (34, 18, 72, 33),
            "mobs": [{"id": 12, "x": 38, "y": 16, "hp_pct": 55, "flags": 1, ...}],
            "loot": [{"id": 71, "x": 35, "y": 19, "value": 150, "type": "sw", "quality": "m", "dist": 5}],
            "belt": ["hp", "mp", "em", "em", "hp", "hp", "rj", "em"]
        }
    """
    state = {
        "tick": 0,
        "floor": 0,
        "me": (0, 0, 100, 100),
        "player": None,  # Main player position (x, y) if companion
        "mobs": [],
        "loot": [],
        "belt": [],  # Belt slots: ["hp", "mp", "em", ...]
        "inventory": [],  # Inventory items: [{"type": "hp", "slot": 5, "quality": "normal", "identified": True}, ...]
        "inv_count": 0,  # Total items in inventory
        "stats": None,  # Stats: {"str": 45, "dex": 30, "mag": 15, "vit": 40, "lvl": 8, "pts": 5, "class": 0, "exp": 1250}
        "in_town": False,  # Town flag
        "npcs": [],  # NPCs: [{"type": "hl", "name": "Pepin", "x": 25, "y": 19, "id": 1}, ...]
        "stores": {},  # Store inventories: {"sm": [...], "hl": [...], ...}
        "gold": 0,  # Companion's gold
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

        # Parse loot: L=id@x,y,value,type,qual;...
        # Type codes: go=gold, sw=sword, ax=axe, bw=bow, etc.
        # Quality codes: n=normal, m=magic, u=unique
        if m := re.search(r'L=([^AE\s]+)', line):
            loot_data = m.group(1)
            for loot_str in loot_data.split(';'):
                if not loot_str:
                    continue

                try:
                    loot_id, rest = loot_str.split('@')
                    parts = rest.split(',')

                    x, y, value = map(int, parts[0:3])

                    # Extract type and quality if available (backward compatible)
                    item_type = parts[3] if len(parts) > 3 else "ms"
                    item_qual = parts[4] if len(parts) > 4 else "n"

                    # Calculate distance
                    me_x, me_y, _, _ = state["me"]
                    dist = abs(x - me_x) + abs(y - me_y)

                    state["loot"].append({
                        "id": int(loot_id),
                        "x": x,
                        "y": y,
                        "value": value,
                        "type": item_type,
                        "quality": item_qual,
                        "dist": dist,
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse loot: {loot_str} - {e}")
                    continue

        # Parse belt: B=hp,mp,em,em,hp,hp,rj,em (8 slots)
        # Types: hp=healing, mp=mana, rj=rejuv, em=empty, ms=misc
        # Scrolls: sh=heal, sp=portal, sr=resurrect, sl=lightning, sf=fireball, si=identify, sc=generic
        if m := re.search(r'B=([a-z,]+)', line):
            belt_data = m.group(1)
            state["belt"] = belt_data.split(',')

        # Parse inventory: INV=type@slot;type@slot;...
        # Types: hp, mp, rj, sw, ax, bw, etc.
        # Quality: _m=magic, _u=unique (e.g., sw_m = magic sword)
        # Identified: ! suffix means unidentified (e.g., sw_m! = unidentified magic sword)
        if m := re.search(r'INV=([^A-Z\s]+)', line):
            inv_data = m.group(1)
            for inv_str in inv_data.split(';'):
                if not inv_str:
                    continue

                try:
                    type_code, slot_str = inv_str.split('@')
                    slot = int(slot_str)

                    # Parse type code with quality/identified flags
                    base_type = type_code
                    quality = "normal"
                    identified = True

                    # Check for unidentified flag (!)
                    if '!' in type_code:
                        identified = False
                        base_type = type_code.replace('!', '')

                    # Check for quality suffix (_m or _u)
                    if base_type.endswith('_m'):
                        quality = "magic"
                        base_type = base_type[:-2]
                    elif base_type.endswith('_u'):
                        quality = "unique"
                        base_type = base_type[:-2]

                    state["inventory"].append({
                        "type": base_type,
                        "slot": slot,
                        "quality": quality,
                        "identified": identified,
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse inventory item: {inv_str} - {e}")
                    continue

        # Parse inventory count: INVC=15
        if m := re.search(r'INVC=(\d+)', line):
            state["inv_count"] = int(m.group(1))

        # Parse equipped gear: EQ=hd:hl_m,hl:sw_u,hr:sh,ch:la_m
        # Slots: hd=head, rl=ring_left, rr=ring_right, am=amulet, hl=hand_left, hr=hand_right, ch=chest
        if m := re.search(r'EQ=([^A-Z\s]+)', line):
            eq_data = m.group(1)
            state["equipped"] = {}

            slot_names = {
                "hd": "head",
                "rl": "ring_left",
                "rr": "ring_right",
                "am": "amulet",
                "hl": "hand_left",
                "hr": "hand_right",
                "ch": "chest",
            }

            for eq_str in eq_data.split(','):
                if not eq_str or ':' not in eq_str:
                    continue

                slot_code, item_type = eq_str.split(':', 1)
                slot_name = slot_names.get(slot_code, slot_code)

                # Parse item type with quality suffix
                quality = "normal"
                if item_type.endswith('_m'):
                    quality = "magic"
                    item_type = item_type[:-2]
                elif item_type.endswith('_u'):
                    quality = "unique"
                    item_type = item_type[:-2]

                state["equipped"][slot_name] = {
                    "type": item_type,
                    "quality": quality,
                }

        # Parse stats: S=str,dex,mag,vit,lvl,pts,class,exp
        # Class: 0=warrior, 1=rogue, 2=sorc, 3=monk, 4=bard, 5=barb
        if m := re.search(r'S=(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)', line):
            state["stats"] = {
                "str": int(m.group(1)),
                "dex": int(m.group(2)),
                "mag": int(m.group(3)),
                "vit": int(m.group(4)),
                "lvl": int(m.group(5)),
                "pts": int(m.group(6)),
                "class": int(m.group(7)),
                "exp": int(m.group(8)),
            }

        # Parse town flag: TN=0 or TN=1
        if m := re.search(r'TN=([01])', line):
            state["in_town"] = m.group(1) == "1"

        # Parse NPCs: NPC=type@x,y,id;...
        # Type codes: sm=Smith, hl=Healer, wt=Witch, tv=Tavern, st=Storyteller, etc.
        if m := re.search(r'NPC=([^E\s]+)', line):
            npc_data = m.group(1)

            # Map NPC type codes to names
            npc_names = {
                "sm": "Griswold",  # Smith (Blacksmith)
                "hl": "Pepin",     # Healer
                "dg": "Wounded Townsman",  # Dead Guy
                "tv": "Ogden",     # Tavern owner
                "cn": "Cain",      # Elder (Storyteller)
                "dr": "Farnham",   # Drunk
                "wt": "Adria",     # Witch
                "bm": "Gillian",   # Barmaid
                "pg": "Wirt",      # Peg-legged boy
                "cw": "Cow",       # Cow
                "fm": "Lester",    # Farmer
                "gl": "Celia",     # Girl
                "cf": "Complete Nut",  # Cowfarm
            }

            for npc_str in npc_data.split(';'):
                if not npc_str:
                    continue

                try:
                    type_code, rest = npc_str.split('@')
                    x, y, npc_id = map(int, rest.split(','))

                    # Calculate distance from player
                    me_x, me_y, _, _ = state["me"]
                    dist = abs(x - me_x) + abs(y - me_y)

                    state["npcs"].append({
                        "type": type_code,
                        "name": npc_names.get(type_code, "NPC"),
                        "x": x,
                        "y": y,
                        "id": npc_id,
                        "dist": dist,
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse NPC: {npc_str} - {e}")
                    continue

        # Parse store inventories: ST_sm=type/qual/price/id,type/qual/price/id,...
        # Store codes: sm=Smith, hl=Healer, wt=Witch, pg=Wirt
        for store_code in ["sm", "hl", "wt", "pg"]:
            pattern = f'ST_{store_code}=([^\\s]+)'
            if m := re.search(pattern, line):
                store_data = m.group(1)
                store_items = []

                for item_str in store_data.split(','):
                    if not item_str:
                        continue

                    try:
                        parts = item_str.split('/')
                        if len(parts) >= 4:
                            item_type, quality, price, item_id = parts[0:4]

                            store_items.append({
                                "type": item_type,
                                "quality": quality,
                                "price": int(price),
                                "id": int(item_id),
                            })
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse store item: {item_str} - {e}")
                        continue

                if store_items:
                    state["stores"][store_code] = store_items

        # Parse gold: GOLD=2500
        if m := re.search(r'GOLD=(\d+)', line):
            state["gold"] = int(m.group(1))

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
