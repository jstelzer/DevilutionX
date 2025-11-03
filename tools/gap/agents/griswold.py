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
        2. Have items worth selling (identified junk)
        """
        if not state.get("in_town", False):
            return False

        # Check if we have sellable items (must be identified first!)
        inventory = state.get("inventory", [])
        sellable_types = ["sw", "ax", "bw", "mc", "sh", "la", "ma", "ha", "hl", "st"]

        # Only sell identified items (avoid selling good unidentified gear)
        # Use character profile if available to filter out items we want to keep
        sellable_items = []
        for item in inventory:
            if item["type"] not in sellable_types:
                continue
            if not item["identified"]:
                continue  # Don't sell unidentified items!

            # Use profile to check if we should keep this item
            if self.profile:
                eval_result = self.profile.should_keep_item(item["type"], item["quality"])
                if eval_result["keep"]:
                    continue  # Profile says keep it
            else:
                # No profile - only sell normal quality
                if item["quality"] != "normal":
                    continue

            sellable_items.append(item)

        return len(sellable_items) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Decide which items to sell.

        Strategy:
        1. Navigate to Griswold if not nearby
        2. Sell identified junk (items profile says we don't want)
        3. Keep magic/unique items appropriate for our class
        4. Prioritize selling when inventory > 40% full
        """
        inventory = state.get("inventory", [])
        inv_count = state.get("inv_count", 0)
        gold = state.get("gold", 0)
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        npcs = state.get("npcs", [])

        # Find sellable items (must match should_activate logic!)
        sellable_types = ["sw", "ax", "bw", "mc", "sh", "la", "ma", "ha", "hl", "st"]
        potential_sells = []
        for item in inventory:
            if item["type"] not in sellable_types:
                continue
            if not item["identified"]:
                continue  # Don't sell unidentified!

            # Use profile to check if we should keep this item
            if self.profile:
                eval_result = self.profile.should_keep_item(item["type"], item["quality"])
                if eval_result["keep"]:
                    continue  # Profile says keep it
            else:
                # No profile - only sell normal quality
                if item["quality"] != "normal":
                    continue

            potential_sells.append(item)

        if not potential_sells:
            return None

        # Find Griswold
        griswold = next((npc for npc in npcs if npc["type"] == "sm"), None)

        if not griswold:
            logger.warning("Griswold: Have sellable items but Griswold not found in NPC list")
            return None

        # Calculate distance to Griswold (use Chebyshev distance)
        gris_x, gris_y = griswold["x"], griswold["y"]
        dist = max(abs(gris_x - me_x), abs(gris_y - me_y))

        # Calculate urgency based on inventory fullness
        inv_fullness = inv_count / 40.0

        # If within interaction range, interact with Griswold to open shop
        if dist <= 3:
            # Close enough - interact with Griswold
            weight = 0.6 if inv_fullness > 0.6 else 0.45
            logger.info(f"Griswold: Interacting with Griswold (dist={dist}, sellable={len(potential_sells)})")
            return AgentResponse(
                command=f"IN {griswold['id']}",
                weight=weight,
                reasoning=f"Griswold: Opening shop to sell {len(potential_sells)} items"
            )

        # If too far, navigate to Griswold first
        if dist > 3:
            # Higher urgency if inventory is fuller
            if inv_fullness > 0.8:
                weight = 0.65
                reasoning = f"Griswold: Going to Griswold (URGENT - inventory {inv_fullness*100:.0f}% full)"
            elif inv_fullness > 0.6:
                weight = 0.5
                reasoning = f"Griswold: Going to Griswold (inventory {inv_fullness*100:.0f}% full)"
            else:
                weight = 0.4
                reasoning = f"Griswold: Going to Griswold ({len(potential_sells)} items to sell)"

            logger.info(f"Griswold: Navigating to Griswold at ({gris_x},{gris_y}), dist={dist}, sellable={len(potential_sells)}")
            return AgentResponse(
                command=f"MV {gris_x} {gris_y}",
                weight=weight,
                reasoning=reasoning
            )

        # Adjacent to Griswold - sell items!
        # (Already filtered above to only include junk)
        sellable_items = potential_sells

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
