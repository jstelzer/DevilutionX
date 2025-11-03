"""
Adria Agent - Witch shop for casters (mana potions, staves, spell books)
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# GBNF grammar for Adria commands
ADRIA_GRAMMAR = r"""
root   ::= (buy | sell | none) "\n"?
buy    ::= "BUY wt " int " " weight
sell   ::= "SELL " int " " weight
none   ::= "NONE " weight
weight ::= "0." digit+ | "1.0" | "1" | "0"
int    ::= digit+
digit  ::= [0-9]
"""


class AdriaAgent(BaseAgent):
    """Specialist for Adria's witch shop - mana potions, staves, books"""

    def __init__(self, **kwargs):
        super().__init__(name="Adria", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Activate if:
        1. In town
        2. Character is a caster (sorcerer or has magic stat investment)
        3. Need mana potions OR have staves/books to sell
        """
        if not state.get("in_town", False):
            return False

        stats = state.get("stats")
        if not stats:
            return False

        # Check if character is a caster
        player_class = stats.get("class", 0)
        is_sorcerer = (player_class == 2)
        is_caster = is_sorcerer or stats.get("mag", 0) > 25  # High magic = caster

        if not is_caster:
            return False

        # Check if we need mana potions
        belt = state.get("belt", [])
        mp_potions = sum(1 for slot in belt if slot == "mp")
        need_mana = mp_potions < 2

        # Check if we have staves/books to sell
        inventory = state.get("inventory", [])
        sellable_magic_items = [
            item for item in inventory
            if item["type"] in ["st", "bk"] and item["identified"]
        ]

        return need_mana or len(sellable_magic_items) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Manage Adria shop interactions.

        Priority:
        1. Navigate to Adria if not nearby
        2. Buy mana potions if low (casters need mana!)
        3. Sell staves/books that we can't use
        4. Buy spell books we can learn
        5. Buy better staves (if profile wants them)
        """
        inventory = state.get("inventory", [])
        inv_count = state.get("inv_count", 0)
        gold = state.get("gold", 0)
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        npcs = state.get("npcs", [])
        belt = state.get("belt", [])
        stores = state.get("stores", {})
        stats = state.get("stats", {})

        # Find Adria
        adria = next((npc for npc in npcs if npc["type"] == "wt"), None)

        if not adria:
            logger.warning("Adria: Character is caster but Adria not found in NPC list")
            return None

        # Calculate distance to Adria (use Chebyshev distance)
        adria_x, adria_y = adria["x"], adria["y"]
        dist = max(abs(adria_x - me_x), abs(adria_y - me_y))

        # Count mana potions
        mp_potions_belt = sum(1 for slot in belt if slot == "mp")
        mp_potions_inv = sum(1 for item in inventory if item["type"] == "mp")
        mp_potions_total = mp_potions_belt + mp_potions_inv

        # If too far, navigate to Adria first
        if dist > 2:
            # Higher urgency if out of mana potions
            if mp_potions_total == 0:
                weight = 0.7
                reasoning = "Adria: Going to Adria (OUT of mana potions!)"
            elif mp_potions_belt < 2:
                weight = 0.6
                reasoning = f"Adria: Going to Adria (low mana: {mp_potions_belt} in belt)"
            else:
                weight = 0.4
                reasoning = "Adria: Going to Adria (shopping)"

            logger.info(f"Adria: Navigating to Adria at ({adria_x},{adria_y}), dist={dist}")
            return AgentResponse(
                command=f"MV {adria_x} {adria_y}",
                weight=weight,
                reasoning=reasoning
            )

        # Near Adria but not adjacent - move closer to open shop
        if dist > 1:
            logger.info(f"Adria: Moving adjacent to Adria (dist={dist})")
            return AgentResponse(
                command=f"MV {adria_x} {adria_y}",
                weight=0.65,
                reasoning="Adria: Moving to open witch shop"
            )

        # Adjacent to Adria - check if shop is open
        if "wt" not in stores or not stores["wt"]:
            # Shop not visible - interact to open
            logger.info(f"Adria: Interacting with Adria to open shop")
            return AgentResponse(
                command=f"IN {adria['id']}",
                weight=0.7,
                reasoning="Adria: Opening witch shop"
            )

        # Shop is open - decide what to do
        witch_items = stores["wt"]

        # Priority 1: Buy mana potions if low
        if mp_potions_total < 4:
            mp_items = [item for item in witch_items if item["type"] == "mp"]

            if mp_items and gold >= mp_items[0]["price"]:
                item = mp_items[0]

                prompt = f"""You are the Adria specialist for a caster. Decide if we should buy mana potions.

Belt mana potions: {mp_potions_belt}
Inventory mana potions: {mp_potions_inv}
Total mana potions: {mp_potions_total}
Mana potion available: {item['price']} gold
Our gold: {gold}
Current MP: {mp_pct}%

Casters need mana to cast spells!

Output ONE line only:
BUY wt {item['id']} <weight>

Weight (0.0-1.0):
- 1.0 = Critical (0 mana potions)
- 0.8 = Urgent (1-2 mana potions)
- 0.6 = Stock up (3-4 mana potions)
- 0.0 = Don't buy

Example: BUY wt {item['id']} 0.8"""

                response = self.query_llm(prompt, grammar=ADRIA_GRAMMAR)

                # Parse response
                parsed = self.parse_weighted_response(response)
                if parsed and parsed.command.startswith("BUY"):
                    parsed.reasoning = f"Adria: Buy mana potion ({item['price']}g, have {mp_potions_total})"
                    logger.info(f"Adria: Recommending BUY wt {item['id']} (mana potion, {item['price']}g)")
                    return parsed
                else:
                    logger.warning(f"Adria: Failed to parse BUY command from LLM: {response}")

        # Priority 2: Sell staves/books we can't use
        sellable_items = [
            item for item in inventory
            if item["type"] in ["st", "bk"] and item["identified"]
        ]

        if sellable_items and inv_count / 40.0 > 0.4:
            item = sellable_items[0]

            # Use character profile to check if we should keep this staff/book
            should_sell = True
            if self.profile and item["type"] == "st":
                eval_result = self.profile.should_keep_item("st", item["quality"])
                if eval_result["keep"]:
                    should_sell = False

            if should_sell:
                prompt = f"""You are the Adria specialist. Decide if we should sell this magic item.

Item: {item['type']} ({item['quality']}) at slot {item['slot']}
Inventory: {inv_count}/40 slots
Current gold: {gold}

Sell items we don't need to free inventory space.

Output ONE line only:
SELL {item['slot']} <weight>

Weight (0.0-1.0):
- 0.6 = Inventory 60%+ full
- 0.4 = Inventory 40%+ full
- 0.0 = Don't sell

Example: SELL {item['slot']} 0.5"""

                response = self.query_llm(prompt, grammar=ADRIA_GRAMMAR)

                parsed = self.parse_weighted_response(response)
                if parsed and parsed.command.startswith("SELL"):
                    parsed.reasoning = f"Adria: Sell {item['type']} (free inventory space)"
                    logger.info(f"Adria: Recommending SELL {item['slot']} ({item['type']})")
                    return parsed

        # Priority 3: Buy staves/books if we want them and can afford them
        if gold > 500 and self.profile:
            # Look for staves (casters might want good staves)
            staff_items = [item for item in witch_items if item["type"] == "st"]

            for item in staff_items:
                if gold < item["price"]:
                    continue

                # Check if profile wants this staff
                eval_result = self.profile.should_keep_item("st", item["quality"])

                if eval_result["keep"] and eval_result["priority"] > 0.6:
                    prompt = f"""You are the Adria specialist. Should we buy this staff?

Staff: {item['type']} ({item['quality']})
Price: {item['price']} gold
Our gold: {gold}
Character evaluation: {eval_result['reason']}

Output ONE line only:
BUY wt {item['id']} <weight>

Weight: 0.5 for useful staves
Example: BUY wt {item['id']} 0.5"""

                    response = self.query_llm(prompt, grammar=ADRIA_GRAMMAR)

                    parsed = self.parse_weighted_response(response)
                    if parsed and parsed.command.startswith("BUY"):
                        parsed.reasoning = f"Adria: Buy {item['type']} ({item['price']}g)"
                        logger.info(f"Adria: Recommending BUY wt {item['id']} ({item['type']}, {item['price']}g)")
                        return parsed

        # No actions needed
        return None
