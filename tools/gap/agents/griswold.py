"""
Griswold Agent - Selling items for gold
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# GBNF grammar for selling commands (SELL slot weight or NONE weight)
GRISWOLD_GRAMMAR = r"""
root   ::= (sell | none) "\n"?
sell   ::= "SELL " int " " weight
none   ::= "NONE " weight
weight ::= "0." digit+ | "1.0" | "1" | "0"
int    ::= digit+
digit  ::= [0-9]
"""


class GriswoldAgent(BaseAgent):
    """Specialist for selling low-value items at Griswold's shop"""

    def __init__(self, **kwargs):
        super().__init__(name="Griswold", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Activate if:
        1. In town
        2. Near Griswold (smith)
        3. Have items worth selling (normal quality weapons/armor)
        """
        if not state.get("in_town", False):
            return False

        # Check if Griswold is nearby
        npcs = state.get("npcs", [])
        griswold = next((npc for npc in npcs if npc["type"] == "sm"), None)

        if not griswold or griswold["dist"] > 3:
            return False

        # Check if we have sellable items
        inventory = state.get("inventory", [])
        sellable_types = ["sw", "ax", "bw", "mc", "sh", "la", "ma", "ha", "hl", "st"]

        # Only sell normal quality items (not magic/unique)
        sellable_items = [
            item for item in inventory
            if item["type"] in sellable_types and item["quality"] == "normal"
        ]

        return len(sellable_items) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Decide which items to sell.

        Strategy:
        1. Sell normal (non-magic) weapons/armor
        2. Keep magic/unique items for identification or use
        3. Prioritize selling when inventory > 50% full
        """
        inventory = state.get("inventory", [])
        inv_count = state.get("inv_count", 0)
        gold = state.get("gold", 0)

        # Find sellable items (normal quality equipment)
        sellable_types = ["sw", "ax", "bw", "mc", "sh", "la", "ma", "ha", "hl", "st"]
        sellable_items = [
            item for item in inventory
            if item["type"] in sellable_types and item["quality"] == "normal"
        ]

        if not sellable_items:
            return None

        # Calculate urgency based on inventory fullness
        inv_fullness = inv_count / 40.0  # 40 = max inventory slots

        # Higher weight if inventory is fuller
        if inv_fullness > 0.8:
            weight = 0.7  # Urgent - inventory almost full
            urgency = "URGENT"
        elif inv_fullness > 0.6:
            weight = 0.5  # Recommended
            urgency = "RECOMMENDED"
        elif inv_fullness > 0.4:
            weight = 0.3  # Optional
            urgency = "OPTIONAL"
        else:
            # Don't bother selling if inventory not filling up
            return None

        # Sell the first sellable item
        item = sellable_items[0]

        prompt = f"""You are the Griswold specialist. Decide if we should sell items.

Inventory: {inv_count}/40 slots ({inv_fullness*100:.0f}% full)
Sellable items: {len(sellable_items)} normal quality equipment
First sellable: {item['type']} at slot {item['slot']}
Current gold: {gold}

Inventory fullness: {urgency}

Output ONE line only:
SELL {item['slot']} <weight>

Weight (0.0-1.0):
- 1.0 = Critical (inventory 90%+ full)
- 0.7 = Urgent (inventory 80%+ full)
- 0.5 = Recommended (inventory 60%+ full)
- 0.0 = Don't sell

Example: SELL {item['slot']} {weight}"""

        response = self.query_llm(prompt, grammar=GRISWOLD_GRAMMAR)

        # Parse response
        parsed = self.parse_weighted_response(response)
        if parsed and parsed.command.startswith("SELL"):
            parsed.reasoning = f"Griswold: Sell {item['type']} (inv {inv_fullness*100:.0f}% full)"
            logger.info(f"Griswold: Recommending SELL slot {item['slot']} ({item['type']}, inv={inv_count}/40)")
            return parsed
        else:
            logger.warning(f"Griswold: Failed to parse SELL command from LLM: {response}")

        return None
