"""
Combat Agent - Offensive decision-making specialist
"""

import logging
import math
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# GBNF grammar for combat commands (AT <id> <weight> or NONE <weight>)
COMBAT_GRAMMAR = r"""
root   ::= (at | none) "\n"?
at     ::= "AT " int " " weight
none   ::= "NONE " weight
weight ::= "0." digit+ | "1.0" | "1" | "0"
int    ::= digit+
digit  ::= [0-9]
"""


class CombatAgent(BaseAgent):
    """Specialist for attack target selection and combat tactics"""

    def __init__(self, **kwargs):
        super().__init__(name="Combat", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Only activate if monsters nearby and not in town"""
        if state.get("in_town", False):
            return False

        mobs = state.get("mobs", [])
        return len(mobs) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Evaluate monsters and recommend best attack target.

        Class-aware tactics:
        - RANGED (Rogue with bow): Kite, prioritize ranged enemies, keep distance
        - MELEE (Warrior): Rush in, tank, prioritize close threats
        - CASTER (Sorcerer): Keep distance, prioritize dangerous targets
        """
        mobs = state.get("mobs", [])
        if not mobs:
            return AgentResponse(command="NONE", weight=0.0)

        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        stats = state.get("stats", {})
        equipped = state.get("equipped", {})

        # Determine combat style from character profile
        combat_style = "melee"  # Default
        playstyle_context = ""

        if self.profile:
            combat_style = self.profile.get_combat_style()
            playstyle_context = self.profile.get_combat_context()
        else:
            # Fallback: check equipped weapon
            weapon = equipped.get("hand_left", {})
            if weapon and weapon.get("type") == "bw":
                combat_style = "ranged"
                playstyle_context = "RANGED FIGHTER - Use bow, keep distance, kite enemies"
            elif stats.get("class") == 2:  # Sorcerer
                combat_style = "caster"
                playstyle_context = "CASTER - Keep distance, prioritize dangerous targets"

        # Build prompt for LLM with class-specific tactics
        mob_list = []
        ranged_count = 0
        melee_count = 0

        for mob in mobs[:8]:  # Top 8 for better context
            mob_id = mob.get("id", 0)
            mob_x = mob.get("x", 0)
            mob_y = mob.get("y", 0)
            mob_hp = mob.get("hp_pct", 100)
            mob_dist = mob.get("dist", 999)
            mob_flags = mob.get("flags", 0)

            # Flag decoding
            is_hostile = (mob_flags & 1) > 0
            is_unique = (mob_flags & 2) > 0
            is_ranged = (mob_flags & 4) > 0

            if is_ranged:
                ranged_count += 1
            else:
                melee_count += 1

            threat_marker = "BOSS" if is_unique else ("ARCHER" if is_ranged else "MELEE")

            mob_list.append(
                f"{mob_id}@{mob_x},{mob_y} HP={mob_hp}% Dist={mob_dist} {threat_marker}"
            )

        # Build class-specific tactical guidance
        if combat_style == "ranged":
            tactics = f"""
YOUR COMBAT ROLE: {playstyle_context}

RANGED TACTICS (BOW USER):
- PRIORITIZE ARCHERS FIRST (let player handle melee)
- Keep distance 6+ tiles from melee enemies (kite!)
- Attack from max range
- If surrounded, target closest threat then retreat

PRIORITY:
1. ARCHERS at medium range (4-8 tiles) - Your specialty!
2. Low HP enemies (finish them off)
3. Enemies charging at you (self-defense)

Current situation: {ranged_count} archers, {melee_count} melee"""

        elif combat_style == "caster":
            tactics = f"""
YOUR COMBAT ROLE: {playstyle_context}

CASTER TACTICS (MAGE):
- Keep distance 5+ tiles
- Prioritize dangerous/boss enemies
- Manage mana (MP={mp_pct}%)

PRIORITY:
1. BOSS/unique monsters (most dangerous)
2. ARCHERS (range threats)
3. Close enemies (defensive)"""

        else:  # melee
            tactics = f"""
YOUR COMBAT ROLE: {playstyle_context}

MELEE TACTICS (WARRIOR):
- Rush close enemies
- Tank damage (HP={hp_pct}%)
- Prioritize immediate threats

PRIORITY:
1. Low HP enemies (finish them)
2. Closest threats (dist < 3)
3. Boss/unique monsters"""

        prompt = f"""You are the Combat specialist. Select the BEST attack target.

Your HP: {hp_pct}%
Your Position: ({me_x},{me_y})
{tactics}

Monsters nearby:
{chr(10).join(mob_list)}

Output ONE line only:
AT <id> <weight>

Weight (0.0-1.0):
- 1.0 = Perfect target (matches your role + high priority)
- 0.8 = Good target (matches tactics)
- 0.6 = Acceptable target
- 0.4 = Suboptimal but acceptable
- 0.0 = No viable target

Example: AT {mobs[0].get('id', 27)} 0.85"""

        response = self.query_llm(prompt, grammar=COMBAT_GRAMMAR)

        # Parse response
        parsed = self.parse_weighted_response(response)
        if not parsed:
            # LLM timeout or parse failure - skip this decision cycle
            # Don't use stale fallback data to avoid spam attacking dead monsters
            logger.warning("Combat: LLM timeout, skipping combat decision to avoid stale targets")
            return None

        if not parsed.command.startswith("AT"):
            # Invalid command format - skip decision
            logger.warning(f"Combat: Invalid command format: {parsed.command}")
            return None

        # RANGED ATTACK POSITIONING:
        # For ranged characters, convert "AT <id>" to position-based attack
        # to prevent pathfinding INTO melee range
        if combat_style == "ranged":
            # Extract monster ID from "AT <id>"
            try:
                monster_id = int(parsed.command.split()[1])

                # Find the monster in our mob list
                target_mob = next((m for m in mobs if m.get("id") == monster_id), None)

                if target_mob:
                    # Get monster position
                    mob_x = target_mob.get("x", 0)
                    mob_y = target_mob.get("y", 0)
                    mob_dist = target_mob.get("dist", 999)

                    # Check if we're already at good range (4-10 tiles)
                    if mob_dist >= 4 and mob_dist <= 10:
                        # Perfect range - attack from current position
                        # Use position-based attack (AT x y) to avoid moving
                        parsed.command = f"AT {mob_x} {mob_y}"
                        parsed.reasoning = f"Combat: Ranged attack at ({mob_x},{mob_y}) dist={mob_dist} [MAINTAINING DISTANCE]"
                        logger.info(f"⚔️ RANGED: Attacking monster {monster_id} at distance {mob_dist} without moving")
                    elif mob_dist < 4:
                        # Too close - kite backwards WHILE attacking
                        # Calculate retreat position (away from monster)
                        retreat_x = me_x + (me_x - mob_x)  # Move away from monster
                        retreat_y = me_y + (me_y - mob_y)

                        # Clamp to reasonable bounds (basic safety)
                        retreat_x = max(0, min(112, retreat_x))
                        retreat_y = max(0, min(112, retreat_y))

                        # ATTACK from position while kiting (don't just run!)
                        parsed.command = f"AT {mob_x} {mob_y}"
                        parsed.reasoning = f"Combat: KITE-ATTACK - shooting while retreating from ({mob_x},{mob_y}) dist={mob_dist}"
                        logger.warning(f"🏹 KITE-ATTACK: Monster {monster_id} too close ({mob_dist} tiles), attacking while repositioning!")
                        # Note: Movement handled by game engine after attack
                    else:
                        # Too far (>10 tiles) - move closer to ~8 tile range
                        # Calculate position 8 tiles from monster (using direction vector)
                        # Direction from monster to companion
                        dx_vec = me_x - mob_x
                        dy_vec = me_y - mob_y
                        dist = math.sqrt(dx_vec * dx_vec + dy_vec * dy_vec)

                        if dist > 0:
                            # Normalize direction and place us 8 tiles from monster
                            target_dist = 8
                            approach_x = mob_x + int((dx_vec / dist) * target_dist)
                            approach_y = mob_y + int((dy_vec / dist) * target_dist)

                            # Clamp to bounds
                            approach_x = max(0, min(112, approach_x))
                            approach_y = max(0, min(112, approach_y))

                            parsed.command = f"MV {approach_x} {approach_y}"
                            parsed.reasoning = f"Combat: Moving to bow range (currently {mob_dist} tiles, target 8 tiles from monster)"
                            logger.info(f"⚔️ RANGED: Closing distance to monster {monster_id} (currently {mob_dist} tiles) - moving to ({approach_x},{approach_y})")
                        else:
                            # Fallback: move toward monster directly
                            parsed.command = f"MV {mob_x} {mob_y}"
                            parsed.reasoning = f"Combat: Moving toward monster {monster_id} (dist={mob_dist})"
                            logger.info(f"⚔️ RANGED: Moving toward monster {monster_id}")

            except (ValueError, IndexError) as e:
                logger.error(f"Combat: Failed to parse monster ID from ranged attack: {e}")
                # Fall through to regular melee attack

        parsed.reasoning = f"Combat: {parsed.command}"
        return parsed
