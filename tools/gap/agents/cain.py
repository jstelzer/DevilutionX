"""
Cain Agent - Identifying magic/unique items
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# GBNF grammar for identify commands (ID slot weight or NONE weight)
CAIN_GRAMMAR = r"""
root   ::= (identify | none) "\n"?
identify ::= "ID " int " " weight
none   ::= "NONE " weight
weight ::= "0." digit+ | "1.0" | "1" | "0"
int    ::= digit+
digit  ::= [0-9]
"""


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

        # Adjacent to Cain - identify items!

        # Prioritize weapon/armor over jewelry
        priority_types = ["sw", "ax", "bw", "mc", "sh", "la", "ma", "ha", "hl", "st"]
        priority_items = [item for item in unidentified if item["type"] in priority_types]

        # Choose item to identify
        if priority_items:
            item = priority_items[0]
        else:
            item = unidentified[0]

        # Calculate urgency
        inv_fullness = inv_count / 40.0
        unid_count = len(unidentified)

        # Higher weight if more unidentified items or inventory filling up
        if unid_count >= 5 or inv_fullness > 0.7:
            weight = 0.8
            urgency = "URGENT"
        elif unid_count >= 3 or inv_fullness > 0.5:
            weight = 0.6
            urgency = "RECOMMENDED"
        else:
            weight = 0.4
            urgency = "OPTIONAL"

        prompt = f"""You are the Cain specialist. Decide if we should identify items.

Unidentified items: {unid_count}
Inventory: {inv_count}/40 slots ({inv_fullness*100:.0f}% full)
First unidentified: {item['type']} ({item['quality']}) at slot {item['slot']}
Current gold: {gold}

Priority: {urgency}

Output ONE line only:
ID {item['slot']} <weight>

Weight (0.0-1.0):
- 1.0 = Critical (many unidentified items blocking inventory)
- 0.8 = Urgent (5+ unidentified or inventory 70%+ full)
- 0.6 = Recommended (3+ unidentified or inventory 50%+ full)
- 0.0 = Don't identify

Example: ID {item['slot']} {weight}"""

        response = self.query_llm(prompt, grammar=CAIN_GRAMMAR)

        # Parse response
        parsed = self.parse_weighted_response(response)
        if parsed and parsed.command.startswith("ID"):
            parsed.reasoning = f"Cain: Identify {item['type']} ({item['quality']}, {unid_count} unid items)"
            logger.info(f"Cain: Recommending ID slot {item['slot']} ({item['type']}, unid_count={unid_count})")
            return parsed
        else:
            logger.warning(f"Cain: Failed to parse ID command from LLM: {response}")

        return None
