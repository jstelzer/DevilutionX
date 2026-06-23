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
        Activate (in town) if:
        - We have staves/books to offload — ANY class, because Adria is the ONLY
          vendor that buys them (Griswold refuses staves), or
        - We're a caster who needs mana potions or has a low staff to recharge.
        """
        if not state.get("in_town", False):
            return False
        stats = state.get("stats")
        if not stats:
            return False

        # Staves/books can only be sold here — universal, not caster-gated.
        if self._sellable_items(state):
            return True

        # Buying mana / recharging is caster-only.
        is_caster = stats.get("class", 0) == 2 or stats.get("mag", 0) > 25
        if not is_caster:
            return False

        mp_potions = sum(1 for slot in state.get("belt", []) if slot == "mp")
        need_mana = mp_potions < 2

        hand_left = state.get("equipped", {}).get("hand_left")
        staff_low_charges = bool(
            hand_left and hand_left.get("type") == "st" and 0 < hand_left.get("charges", 0) <= 5
        )
        return need_mana or staff_low_charges

    def _sellable_items(self, state: Dict[str, Any]) -> list:
        """Identified staves/books worth offloading (profile doesn't want to keep)."""
        items = []
        for item in state.get("inventory", []):
            if item.get("type") not in ("st", "bk"):
                continue
            if not item.get("identified"):
                continue
            if self.profile and item["type"] == "st":
                if self.profile.should_keep_item("st", item.get("quality", "normal")).get("keep"):
                    continue
            items.append(item)
        return items

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

        # Priority 0: Check if equipped staff needs recharging
        # Note: Actual recharging requires UI interaction not yet implemented for GAP
        # For now, just log a warning when staff is low on charges
        hand_left = state.get("equipped", {}).get("hand_left")
        if hand_left and hand_left.get("type") == "st":
            staff_charges = hand_left.get("charges", 0)
            if 0 < staff_charges <= 5:
                logger.warning(f"⚡ Adria: Equipped staff has LOW charges ({staff_charges})! "
                              f"Recharging not yet implemented for GAP - consider manual recharge")
            elif staff_charges == 0:
                logger.warning(f"⚡ Adria: Equipped staff has NO charges! "
                              f"Recharging not yet implemented for GAP - staff is useless until recharged")

        # Priority 1: Buy mana potions if low (casters only — a Warrior offloading
        # a looted staff shouldn't stock mana).
        is_caster = stats.get("class", 0) == 2 or stats.get("mag", 0) > 25
        if is_caster and mp_potions_total < 4:
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

        # Priority 2: Sell staves/books (deterministic — selling is mechanical, no
        # LLM needed; one per tick clears them over ticks). Urgency scales with how
        # full the GRID is (free cells), not item count.
        sellable_items = self._sellable_items(state)
        if sellable_items:
            inv_free = state.get("inv_free", 40)
            if inv_free <= 4:
                weight = 0.7   # grid nearly full — offload now
            elif inv_free <= 12:
                weight = 0.5
            else:
                weight = 0.3   # shop's open anyway, might as well
            item = sellable_items[0]
            logger.info(f"Adria: SELL slot {item['slot']} ({item['quality']}/{item['type']}), inv_free={inv_free}")
            return AgentResponse(
                command=f"SELL {item['slot']}",
                weight=weight,
                reasoning=f"Adria: sell {item['quality']}/{item['type']} (free {inv_free} cells)"
            )

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
