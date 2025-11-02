"""
Shopping Agent - Manages buying potions, selling junk, and repairs
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# GBNF grammar for shopping commands (BUY npc id weight or NONE weight)
SHOPPING_GRAMMAR = r"""
root   ::= (buy | sell | repair | none) "\n"?
buy    ::= "BUY " npc " " int " " weight
sell   ::= "SELL " int " " weight
repair ::= "REP " int " " weight
none   ::= "NONE " weight
npc    ::= "sm" | "hl" | "wt" | "pg"
weight ::= "0." digit+ | "1.0" | "1" | "0"
int    ::= digit+
digit  ::= [0-9]
"""


class ShoppingAgent(BaseAgent):
    """Specialist for town commerce - buying potions, selling junk"""

    def __init__(self, **kwargs):
        super().__init__(name="Shopping", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Only activate in town with available stores"""
        if not state.get("in_town", False):
            return False

        stores = state.get("stores", {})
        return len(stores) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Evaluate shopping needs and recommend action.

        Priority:
        1. Buy health potions if belt has < 3
        2. Sell junk items if inventory > 80% full (future)
        3. Repair damaged equipment (future)
        """
        belt = state.get("belt", [])
        stores = state.get("stores", {})
        gold = state.get("gold", 0)

        # Count available health potions in belt
        hp_potions = sum(1 for slot in belt if slot == "hp")

        # Check if we need to buy health potions
        if hp_potions < 3 and "hl" in stores:
            # Look for health potions at healer
            healer_items = stores["hl"]
            hp_items = [item for item in healer_items if item["type"] == "hp"]

            if hp_items and gold >= hp_items[0]["price"]:
                # Buy the first (cheapest) health potion
                item = hp_items[0]

                prompt = f"""You are the Shopping specialist. Decide if we should buy potions.

Belt: {belt}
HP Potions in belt: {hp_potions}
Healer inventory: {len(healer_items)} items
HP Potion available: {item['price']} gold
Our gold: {gold}

We need more health potions (have {hp_potions}, want 3+).

Output ONE line only:
BUY hl {item['id']} <weight>

Weight (0.0-1.0):
- 1.0 = Critical need (0-1 potions)
- 0.8 = Urgent need (2 potions)
- 0.5 = Stock up (3-4 potions)
- 0.0 = Don't buy

Example: BUY hl 1 0.9"""

                response = self.query_llm(prompt, grammar=SHOPPING_GRAMMAR)

                # Parse response
                parsed = self.parse_weighted_response(response)
                if parsed and parsed.command.startswith("BUY"):
                    parsed.reasoning = f"Shopping: Buy health potion ({item['price']}g)"
                    return parsed

        # Check for mana potions (if we're a caster)
        stats = state.get("stats")
        if stats:
            player_class = stats.get("class", 0)
            # Class 2 = Sorcerer, check if mana is low
            if player_class == 2:
                mp_potions = sum(1 for slot in belt if slot == "mp")

                if mp_potions < 2 and "hl" in stores:
                    healer_items = stores["hl"]
                    mp_items = [item for item in healer_items if item["type"] == "mp"]

                    if mp_items and gold >= mp_items[0]["price"]:
                        item = mp_items[0]

                        prompt = f"""You are the Shopping specialist for a sorcerer.

Belt: {belt}
Mana Potions in belt: {mp_potions}
Mana Potion available: {item['price']} gold
Our gold: {gold}

We need mana potions for spellcasting.

Output ONE line only:
BUY hl {item['id']} <weight>

Weight: 0.7 for mana potions (important but not as critical as HP)

Example: BUY hl 2 0.7"""

                        response = self.query_llm(prompt, grammar=SHOPPING_GRAMMAR)

                        parsed = self.parse_weighted_response(response)
                        if parsed and parsed.command.startswith("BUY"):
                            parsed.reasoning = f"Shopping: Buy mana potion ({item['price']}g)"
                            return parsed

        # No shopping needs right now
        return None
