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
        "player_floor": None,  # Main player's dungeon level (for follow decisions)
        "stairs": [],  # Level-transition triggers: [{"type": "down"|"up", "x": .., "y": ..}, ...]
        "portals": [],  # Town portals: [{"x": .., "y": .., "caster": "me"|"them"}, ...]
        "mobs": [],
        "loot": [],
        "objects": [],  # Objects: [{"id": 15, "x": 45, "y": 30, "type": "ch", "dist": 5}, ...]
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

        # Parse floor: F=2 (lookbehind avoids matching the F in PF=)
        if m := re.search(r'(?<![A-Za-z])F=(\d+)', line):
            state["floor"] = int(m.group(1))

        # Parse player: ME=x,y,hp%,mp%
        if m := re.search(r'ME=(\d+),(\d+),(\d+),(\d+)', line):
            state["me"] = tuple(map(int, m.groups()))

        # Parse main player position: PLYR=x,y
        if m := re.search(r'PLYR=(\d+),(\d+)', line):
            state["player"] = tuple(map(int, m.groups()))

        # Parse main player floor: PF=2 (for deciding to follow across levels)
        if m := re.search(r'PF=(\d+)', line):
            state["player_floor"] = int(m.group(1))

        # Parse level-transition triggers: ST=down@25,29;up@49,21 (a list — the
        # real trigger tiles the engine fires on when standing on them).
        if m := re.search(r'ST=([a-z]+@\d+,\d+(?:;[a-z]+@\d+,\d+)*)', line):
            stairs = []
            for part in m.group(1).split(';'):
                if pm := re.match(r'([a-z]+)@(\d+),(\d+)', part):
                    stairs.append({
                        "type": pm.group(1),  # "down" or "up"
                        "x": int(pm.group(2)),
                        "y": int(pm.group(3)),
                    })
            state["stairs"] = stairs

        # Parse town portals: TP=25,29,them;40,50,me  (caster is "me" or "them")
        if m := re.search(r'TP=(\d+,\d+,[a-z]+(?:;\d+,\d+,[a-z]+)*)', line):
            portals = []
            for part in m.group(1).split(';'):
                if pm := re.match(r'(\d+),(\d+),([a-z]+)', part):
                    portals.append({
                        "x": int(pm.group(1)),
                        "y": int(pm.group(2)),
                        "caster": pm.group(3),  # "me" (our portal) or "them"
                    })
            state["portals"] = portals

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

        # Parse objects: OBJ=id@x,y,type;...
        # Type codes: ch=chest, tc=trapped_chest, dr=door, ba=barrel, xb=explosive_barrel, sh=shrine
        if m := re.search(r'OBJ=([^A-Z\s]+)', line):
            object_data = m.group(1)
            for obj_str in object_data.split(';'):
                if not obj_str:
                    continue

                try:
                    obj_id, rest = obj_str.split('@')
                    parts = rest.split(',')

                    x, y = int(parts[0]), int(parts[1])
                    obj_type = parts[2] if len(parts) > 2 else "unknown"

                    # Calculate distance
                    me_x, me_y, _, _ = state["me"]
                    dist = abs(x - me_x) + abs(y - me_y)

                    state["objects"].append({
                        "id": int(obj_id),
                        "x": x,
                        "y": y,
                        "type": obj_type,
                        "dist": dist,
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse object: {obj_str} - {e}")
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
        # Stats (identified equipment): type:stats@slot
        #   - Weapons: "sw_m:3-6+2:15@5" = magic sword, 3-6 dmg +2 bonus, +15 ToHit, slot 5
        #   - Armor: "la_m:25+5@3" = magic light armor, 25 AC +5 Str, slot 3
        if m := re.search(r'INV=([^A-Z\s]+)', line):
            inv_data = m.group(1)
            for inv_str in inv_data.split(';'):
                if not inv_str:
                    continue

                try:
                    # Split by @ to get type_code and slot
                    type_code, slot_str = inv_str.split('@')
                    slot = int(slot_str)

                    # Parse stats if present (identified equipment has :stats before @slot)
                    stats = None
                    if ':' in type_code:
                        # Split on FIRST colon to separate type from stats
                        parts = type_code.split(':', 1)
                        type_code = parts[0]
                        stat_str = parts[1]

                        # Parse weapon stats: "3-6+2:15" or armor stats: "25+5"
                        if '-' in stat_str:  # Weapon: damage-range
                            # Format: minDam-maxDam+bonus:toHit
                            try:
                                dam_part, tohit_str = stat_str.split(':', 1)
                                # Parse damage: "3-6+2" or "3-6"
                                if '+' in dam_part:
                                    dam_range, dam_bonus = dam_part.split('+')
                                    min_dam, max_dam = map(int, dam_range.split('-'))
                                    dam_bonus = int(dam_bonus)
                                else:
                                    min_dam, max_dam = map(int, dam_part.split('-'))
                                    dam_bonus = 0

                                tohit = int(tohit_str)

                                stats = {
                                    "min_dam": min_dam,
                                    "max_dam": max_dam,
                                    "dam_bonus": dam_bonus,
                                    "to_hit": tohit,
                                }
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Failed to parse weapon stats {stat_str}: {e}")
                        else:  # Armor: AC or AC+bonus
                            try:
                                if '+' in stat_str:
                                    ac_str, bonus_str = stat_str.split('+')
                                    stats = {
                                        "ac": int(ac_str),
                                        "stat_bonus": int(bonus_str),
                                    }
                                else:
                                    stats = {
                                        "ac": int(stat_str),
                                        "stat_bonus": 0,
                                    }
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Failed to parse armor stats {stat_str}: {e}")

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

                    inv_item = {
                        "type": base_type,
                        "slot": slot,
                        "quality": quality,
                        "identified": identified,
                    }

                    # Add stats if present
                    if stats:
                        inv_item["stats"] = stats

                    state["inventory"].append(inv_item)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse inventory item: {inv_str} - {e}")
                    continue

        # Parse inventory count: INVC=15
        if m := re.search(r'INVC=(\d+)', line):
            state["inv_count"] = int(m.group(1))

        # Parse equipped gear: EQ=hd:hl_m,hl:sw_u,hr:sh,ch:la_m
        # Slots: hd=head, rl=ring_left, rr=ring_right, am=amulet, hl=hand_left, hr=hand_right, ch=chest
        # Staves with charges: hl:st_m^12:2 (magic staff with 12 charges of spell ID 2)
        # Equipment stats: hl:sw_m:3-6+2:15 (magic sword, 3-6 dmg +2 bonus, +15 ToHit)
        #                  ch:la_m:25+5 (magic light armor, 25 AC +5 Str)
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

                # Split on FIRST colon to get slot_code and item_data
                parts = eq_str.split(':', 1)
                slot_code = parts[0]
                item_data = parts[1]
                slot_name = slot_names.get(slot_code, slot_code)

                # Parse stats if present (after item type, before charges)
                # Format: type:stats or type^charges:spell or type:stats^charges:spell
                stats = None

                # First handle charges (for staves)
                charges = 0
                spell_id = None
                if '^' in item_data:
                    item_type, charge_data = item_data.split('^', 1)
                    # charge_data could be "12:2" (charges:spell_id) or just "12"
                    if ':' in charge_data:
                        charges_str, spell_str = charge_data.split(':', 1)
                        charges = int(charges_str)
                        spell_id = int(spell_str)
                    else:
                        charges = int(charge_data)
                else:
                    item_type = item_data

                # Now parse stats from item_type (if present)
                # Stats appear after type code: "sw_m:3-6+2:15" or "la_m:25+5"
                if ':' in item_type:
                    # Split on colons to separate type from stats
                    type_parts = item_type.split(':')
                    item_type = type_parts[0]  # First part is always type code

                    # Remaining parts are stats
                    if len(type_parts) >= 2:
                        stat_str = ':'.join(type_parts[1:])  # Rejoin in case of weapon stats (dam:tohit)

                        # Parse weapon stats: "3-6+2:15:45/60" or armor stats: "25+5:40/50"
                        if '-' in stat_str:  # Weapon: damage-range
                            try:
                                parts = stat_str.split(':')
                                dam_part = parts[0]
                                tohit_str = parts[1]

                                if '+' in dam_part:
                                    dam_range, dam_bonus = dam_part.split('+')
                                    min_dam, max_dam = map(int, dam_range.split('-'))
                                    dam_bonus = int(dam_bonus)
                                else:
                                    min_dam, max_dam = map(int, dam_part.split('-'))
                                    dam_bonus = 0

                                tohit = int(tohit_str)

                                stats = {
                                    "min_dam": min_dam,
                                    "max_dam": max_dam,
                                    "dam_bonus": dam_bonus,
                                    "to_hit": tohit,
                                }

                                # Parse durability if present (parts[2] = "45/60")
                                if len(parts) > 2 and '/' in parts[2]:
                                    dur, max_dur = map(int, parts[2].split('/'))
                                    stats["durability"] = dur
                                    stats["max_durability"] = max_dur
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Failed to parse equipped weapon stats {stat_str}: {e}")
                        else:  # Armor: AC or AC+bonus:dur/maxDur
                            try:
                                # Split by colon to separate stats from durability
                                armor_parts = stat_str.split(':')
                                ac_part = armor_parts[0]

                                if '+' in ac_part:
                                    ac_str, bonus_str = ac_part.split('+')
                                    stats = {
                                        "ac": int(ac_str),
                                        "stat_bonus": int(bonus_str),
                                    }
                                else:
                                    stats = {
                                        "ac": int(ac_part),
                                        "stat_bonus": 0,
                                    }

                                # Parse durability if present (armor_parts[1] = "40/50")
                                if len(armor_parts) > 1 and '/' in armor_parts[1]:
                                    dur, max_dur = map(int, armor_parts[1].split('/'))
                                    stats["durability"] = dur
                                    stats["max_durability"] = max_dur
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Failed to parse equipped armor stats {stat_str}: {e}")

                # Parse item type with quality suffix
                quality = "normal"
                if item_type.endswith('_m'):
                    quality = "magic"
                    item_type = item_type[:-2]
                elif item_type.endswith('_u'):
                    quality = "unique"
                    item_type = item_type[:-2]

                equipped_item = {
                    "type": item_type,
                    "quality": quality,
                }

                # Add stats if present
                if stats:
                    equipped_item["stats"] = stats

                # Add charges and spell if present (staves)
                if charges > 0:
                    equipped_item["charges"] = charges
                if spell_id is not None:
                    equipped_item["spell_id"] = spell_id

                state["equipped"][slot_name] = equipped_item

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
