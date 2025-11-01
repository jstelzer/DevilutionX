"""
Combat Agent - Offensive decision-making specialist
"""

import logging
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

        Prioritizes:
        - Low HP monsters (finish them off)
        - Close monsters (immediate threats)
        - Unique/boss monsters (high threat)
        """
        mobs = state.get("mobs", [])
        if not mobs:
            return AgentResponse(command="NONE", weight=0.0)

        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])

        # Build prompt for LLM
        mob_list = []
        for mob in mobs[:5]:  # Top 5 closest
            mob_id = mob.get("id", 0)
            mob_x = mob.get("x", 0)
            mob_y = mob.get("y", 0)
            mob_hp = mob.get("hp_pct", 100)  # Parser uses "hp_pct" not "hp"
            mob_dist = mob.get("dist", 999)
            mob_flags = mob.get("flags", 0)

            # Flag decoding
            is_hostile = (mob_flags & 1) > 0
            is_unique = (mob_flags & 2) > 0
            is_ranged = (mob_flags & 4) > 0

            threat_marker = "BOSS" if is_unique else ("RANGED" if is_ranged else "")

            mob_list.append(
                f"{mob_id}@{mob_x},{mob_y} HP={mob_hp}% Dist={mob_dist} {threat_marker}"
            )

        prompt = f"""You are the Combat specialist. Rate the BEST attack target.

Your HP: {hp_pct}%
Your Position: ({me_x},{me_y})

Monsters nearby:
{chr(10).join(mob_list)}

Output ONE line only:
AT <id> <weight>

Weight (0.0-1.0):
- 1.0 = Low HP (<30%), immediate threat, close (<5 tiles)
- 0.8 = Boss/unique, moderate threat
- 0.6 = Healthy enemy, close
- 0.4 = Distant enemy
- 0.0 = No viable target

Example: AT 27 0.85"""

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

        parsed.reasoning = f"Combat: {parsed.command}"
        return parsed
