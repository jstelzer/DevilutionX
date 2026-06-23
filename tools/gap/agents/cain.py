"""
Cain Agent - Identifying magic/unique items
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class CainAgent(BaseAgent):
    """Specialist for identifying unidentified magic/unique items"""

    def __init__(self, **kwargs):
        super().__init__(name="Cain", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Activate if:
        1. In town
        2. Have unidentified items
        """
        if not state.get("in_town", False):
            return False

        # Check if we have unidentified items
        inventory = state.get("inventory", [])
        unidentified = [item for item in inventory if not item["identified"]]

        return len(unidentified) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Decide which items to identify.

        Strategy:
        1. Navigate to Cain if not nearby
        2. Identify all unidentified magic/unique items
        3. Prioritize weapons and armor (more valuable than jewelry)
        4. Higher priority when inventory is filling up (need to know what to keep/sell)
        """
        inventory = state.get("inventory", [])
        inv_count = state.get("inv_count", 0)
        gold = state.get("gold", 0)
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        npcs = state.get("npcs", [])

        # Find unidentified items
        unidentified = [item for item in inventory if not item["identified"]]

        if not unidentified:
            return None

        # Find Cain
        cain = next((npc for npc in npcs if npc["type"] == "cn"), None)

        if not cain:
            logger.warning("Cain: Have unidentified items but Cain not found in NPC list")
            return None

        # Calculate distance to Cain (use Chebyshev distance like C++)
        cain_x, cain_y = cain["x"], cain["y"]
        dist = max(abs(cain_x - me_x), abs(cain_y - me_y))

        # If too far, navigate to Cain first
        if dist > 1:
            # Higher urgency if many unidentified items
            unid_count = len(unidentified)
            if unid_count >= 5 or inv_count / 40.0 > 0.7:
                weight = 0.75
                reasoning = f"Cain: Going to Cain (URGENT - {unid_count} unidentified items)"
            elif unid_count >= 3:
                weight = 0.6
                reasoning = f"Cain: Going to Cain ({unid_count} unidentified items)"
            else:
                weight = 0.5
                reasoning = f"Cain: Going to Cain ({unid_count} unidentified items)"

            logger.info(f"Cain: Navigating to Cain at ({cain_x},{cain_y}), dist={dist}, unid_count={unid_count}")
            return AgentResponse(
                command=f"MV {cain_x} {cain_y}",
                weight=weight,
                reasoning=reasoning
            )

        # Adjacent to Cain - identify the highest-priority unidentified item.
        # Deterministic (no LLM): IDing is purely mechanical, and an LLM here just
        # risks echoing the wrong slot (cf. the old shopping-agent misfire). One ID
        # per tick naturally loops through the whole pack over successive ticks.
        item = self._best_unidentified(unidentified)

        inv_fullness = inv_count / 40.0
        unid_count = len(unidentified)
        if unid_count >= 5 or inv_fullness > 0.7:
            weight = 0.8
        elif unid_count >= 3 or inv_fullness > 0.5:
            weight = 0.6
        else:
            weight = 0.4

        logger.info(
            f"Cain: ID slot {item['slot']} ({item['quality']}/{item['type']}), "
            f"{unid_count} unidentified remaining"
        )
        return AgentResponse(
            command=f"ID {item['slot']}",
            weight=weight,
            reasoning=f"Cain: Identify {item['quality']}/{item['type']} ({unid_count} unid left)"
        )

    def _best_unidentified(self, unidentified: list) -> Dict[str, Any]:
        """Pick which unidentified item to ID next.

        Class-appropriate gear first (a Rogue's magic bow before a random magic
        sword) so the items most likely to be kept/equipped get IDed before she
        leaves town; then jewelry (often valuable), then other equipment, then
        the rest. Unique before magic within a tier.
        """
        preferred = set()
        if self.profile:
            preferred = set(self.profile.preferred_weapons) | set(self.profile.preferred_armor)
        jewelry = ("rg", "am")
        equipment = ("sw", "ax", "bw", "mc", "sh", "la", "ma", "ha", "hl", "st")
        quality_rank = {"unique": 0, "u": 0, "magic": 1, "m": 1}

        def type_rank(item):
            t = item.get("type")
            if t in preferred:
                return 0
            if t in jewelry:
                return 1
            if t in equipment:
                return 2
            return 3

        return sorted(
            unidentified,
            key=lambda it: (type_rank(it), quality_rank.get(it.get("quality"), 2))
        )[0]
