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
        # Repairs we can't afford: body_index we tried to repair but gold didn't
        # drop (the engine rejected it). Stops her wedging at the smith forever.
        self.unaffordable_repairs = set()
        self._pending_repair_slot = None  # slot we issued REPAIR for last tick
        self._gold_at_repair = None       # gold when we issued it
        self._last_seen_gold = None       # to detect when she gains gold

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Activate if:
        1. In town
        2. Have items worth selling (identified junk) OR
        3. Have damaged equipment that needs repair
        """
        if not state.get("in_town", False):
            return False

        # Check for damaged equipment needing repair
        if self._has_damaged_equipment(state):
            return True

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
        Decide which items to sell or repair.

        Strategy:
        1. PRIORITY: Repair damaged equipment (durability < 75%)
        2. Navigate to Griswold if not nearby
        3. Sell identified junk (items profile says we don't want)
        4. Keep magic/unique items appropriate for our class
        5. Prioritize repairs/selling when inventory > 40% full
        """
        inventory = state.get("inventory", [])
        inv_count = state.get("inv_count", 0)
        gold = state.get("gold", 0)
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        npcs = state.get("npcs", [])
        stores = state.get("stores", {})

        # Find Griswold first (needed for both repair and selling)
        griswold = next((npc for npc in npcs if npc["type"] == "sm"), None)
        if not griswold:
            logger.warning("Griswold: Need Griswold but he's not found in NPC list")
            return None

        gris_x, gris_y = griswold["x"], griswold["y"]
        dist = max(abs(gris_x - me_x), abs(gris_y - me_y))

        # Detect a repair that didn't go through: last tick we issued REPAIR but
        # gold didn't drop -> the engine rejected it (can't afford). Mark the slot
        # unaffordable so we stop looping at the smith.
        if self._pending_repair_slot is not None:
            if gold >= self._gold_at_repair:
                self.unaffordable_repairs.add(self._pending_repair_slot)
                logger.info(
                    f"Griswold: can't afford repair of slot {self._pending_repair_slot} "
                    f"(gold {gold} unchanged); deferring until we have more gold"
                )
            self._pending_repair_slot = None

        # If we've gained gold since last tick (sold something, looted a pile),
        # retry the repairs we previously deferred as unaffordable.
        if (self.unaffordable_repairs and self._last_seen_gold is not None
                and gold > self._last_seen_gold):
            self.unaffordable_repairs.clear()
        self._last_seen_gold = gold

        # PRIORITY 1: Repair damaged equipment (skip ones we can't afford yet)
        damaged_items = [
            d for d in self._find_damaged_equipment(state)
            if d[3] not in self.unaffordable_repairs
        ]
        if damaged_items:
            slot_name, item, dur_pct, body_index = damaged_items[0]  # Most damaged

            # Navigate if too far
            if dist > 3:
                weight = 0.75 if dur_pct < 30.0 else 0.6
                urgency = "URGENT" if dur_pct < 30.0 else "RECOMMENDED"
                logger.info(f"Griswold: Navigating to repair {slot_name} ({dur_pct:.0f}% durability)")
                return AgentResponse(
                    command=f"MV {gris_x} {gris_y}",
                    weight=weight,
                    reasoning=f"Griswold: Going to repair {slot_name} ({urgency})"
                )

            # At Griswold - repair the item. Record the attempt so next tick we
            # can tell whether it actually went through (gold dropped) or was
            # rejected for lack of gold (gold unchanged -> defer it).
            self._pending_repair_slot = body_index
            self._gold_at_repair = gold
            weight = 0.8 if dur_pct < 30.0 else 0.65
            logger.info(f"Griswold: Repairing {slot_name} ({item['type']}, {dur_pct:.0f}% durability)")
            return AgentResponse(
                command=f"REPAIR {body_index}",
                weight=weight,
                reasoning=f"Griswold: Repair {slot_name} ({dur_pct:.0f}% durability)"
            )

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

        # Calculate urgency based on inventory fullness (Griswold already found above)
        inv_fullness = inv_count / 40.0

        # Check if Griswold's shop is currently open
        shop_is_open = "sm" in stores and len(stores.get("sm", [])) > 0

        # If shop is OPEN, sell items
        if shop_is_open:
            # Shop is open - proceed to selling logic below
            logger.info(f"Griswold: Shop is open, proceeding to sell items")
        # If shop is NOT open, navigate and interact to open it
        elif dist <= 3:
            # Close enough - interact with Griswold to open shop
            weight = 0.6 if inv_fullness > 0.6 else 0.45
            logger.info(f"Griswold: Interacting with Griswold to open shop (dist={dist}, sellable={len(potential_sells)})")
            return AgentResponse(
                command=f"IN {griswold['id']}",
                weight=weight,
                reasoning=f"Griswold: Opening shop to sell {len(potential_sells)} items"
            )
        else:  # dist > 3
            # Too far - navigate to Griswold first
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

        # SELLING LOGIC: Shop is open, sell items!
        # (Already filtered above to only include junk)
        sellable_items = potential_sells

        # Calculate weight/urgency based on inventory fullness
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
            # Shop is already open, might as well sell even if inventory not full
            weight = 0.25  # Low priority
            urgency = "OPTIONAL"

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

    def _has_damaged_equipment(self, state: Dict[str, Any]) -> bool:
        """
        Check if any equipped gear needs repair (durability < 75%).

        Returns:
            True if any equipped item needs repair
        """
        equipped = state.get("equipped", {})

        for slot_name, item in equipped.items():
            stats = item.get("stats")
            if not stats:
                continue

            # Check durability
            durability = stats.get("durability")
            max_durability = stats.get("max_durability")

            if durability is not None and max_durability is not None and max_durability > 0:
                dur_pct = (durability / max_durability) * 100
                # Repair if below 75% durability
                if dur_pct < 75.0:
                    logger.info(f"Griswold: {slot_name} ({item['type']}) needs repair: {durability}/{max_durability} ({dur_pct:.0f}%)")
                    return True

        return False

    def _find_damaged_equipment(self, state: Dict[str, Any]) -> list:
        """
        Find all equipped items needing repair.

        Returns:
            List of (slot_name, item, durability_pct, body_index) tuples
        """
        damaged_items = []
        equipped = state.get("equipped", {})

        # Map friendly slot names to body slot indexes for REPAIR command
        slot_to_body_index = {
            "head": 0,           # INVLOC_HEAD
            "ring_left": 1,      # INVLOC_RING_LEFT
            "ring_right": 2,     # INVLOC_RING_RIGHT
            "amulet": 3,         # INVLOC_AMULET
            "hand_left": 4,      # INVLOC_HAND_LEFT
            "hand_right": 5,     # INVLOC_HAND_RIGHT
            "chest": 6,          # INVLOC_CHEST
        }

        for slot_name, item in equipped.items():
            stats = item.get("stats")
            if not stats:
                continue

            durability = stats.get("durability")
            max_durability = stats.get("max_durability")

            if durability is not None and max_durability is not None and max_durability > 0:
                dur_pct = (durability / max_durability) * 100
                if dur_pct < 75.0:
                    body_index = slot_to_body_index.get(slot_name, -1)
                    if body_index >= 0:
                        damaged_items.append((slot_name, item, dur_pct, body_index))

        # Sort by durability (most damaged first)
        damaged_items.sort(key=lambda x: x[2])
        return damaged_items
