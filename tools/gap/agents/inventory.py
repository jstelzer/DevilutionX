"""
Inventory Agent - Belt refill and inventory management
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class InventoryAgent(BaseAgent):
    """Specialist for inventory management - refilling belt from inventory"""

    def __init__(self, **kwargs):
        super().__init__(name="Inventory", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Activate if:
        1. Belt has empty slots
        2. Inventory has potions/scrolls that could fill belt
        """
        belt = state.get("belt", [])
        inventory = state.get("inventory", [])

        # Check if belt has empty slots
        has_empty_belt = any(slot == "em" for slot in belt)

        # Check if inventory has consumables (potions/scrolls)
        consumable_types = ["hp", "mp", "rj", "sh", "sp", "sr", "si", "sl", "sf", "sc"]
        has_consumables = any(item["type"] in consumable_types for item in inventory)

        return has_empty_belt and has_consumables

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Refill belt with potions/scrolls from inventory.

        Priority:
        1. Health potions (hp, rj) → fill belt slots
        2. Mana potions (mp) → fill belt slots (if caster)
        3. Healing scrolls (sh) → backup for health
        4. Other scrolls → utility slots

        Returns MV command to refill belt slot from inventory slot.
        Format: MV inv_slot belt_slot (future - not implemented in C++ yet)

        For now, return NONE and log the need for belt refill.
        This agent serves as a detection/notification system.
        """
        belt = state.get("belt", [])
        inventory = state.get("inventory", [])
        stats = state.get("stats", {})

        # Find empty belt slots
        empty_belt_slots = [i for i, slot in enumerate(belt) if slot == "em"]

        if not empty_belt_slots:
            return None

        # Categorize inventory items
        hp_items = [item for item in inventory if item["type"] in ["hp", "rj"]]
        mp_items = [item for item in inventory if item["type"] == "mp"]
        heal_scrolls = [item for item in inventory if item["type"] == "sh"]
        portal_scrolls = [item for item in inventory if item["type"] == "sp"]

        # Count belt contents
        belt_hp = sum(1 for slot in belt if slot in ["hp", "rj"])
        belt_mp = sum(1 for slot in belt if slot == "mp"]

        # Priority 1: Fill belt with health potions (want 4-6 slots)
        if belt_hp < 4 and hp_items:
            item = hp_items[0]
            belt_slot = empty_belt_slots[0]

            logger.info(f"Inventory: Would move {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return AgentResponse(
                command="NONE",  # Not implemented yet - needs C++ backend
                weight=0.0,  # Don't override other agents
                reasoning=f"Inventory: Need to refill belt with {item['type']} (inv→belt not implemented)"
            )

        # Priority 2: Fill belt with mana potions (casters only, want 2-3 slots)
        player_class = stats.get("class", 0)
        if player_class == 2 and belt_mp < 2 and mp_items:  # Sorcerer
            item = mp_items[0]
            belt_slot = empty_belt_slots[0]

            logger.info(f"Inventory: Would move {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return AgentResponse(
                command="NONE",
                weight=0.0,
                reasoning=f"Inventory: Need to refill belt with {item['type']} (inv→belt not implemented)"
            )

        # Priority 3: Add healing scrolls as backup
        if belt_hp < 2 and heal_scrolls:
            item = heal_scrolls[0]
            belt_slot = empty_belt_slots[0]

            logger.info(f"Inventory: Would move {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return AgentResponse(
                command="NONE",
                weight=0.0,
                reasoning=f"Inventory: Need to refill belt with {item['type']} scroll (inv→belt not implemented)"
            )

        # Priority 4: Add town portal scrolls for convenience
        if len(empty_belt_slots) >= 2 and portal_scrolls:
            item = portal_scrolls[0]
            belt_slot = empty_belt_slots[0]

            logger.info(f"Inventory: Would move {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return AgentResponse(
                command="NONE",
                weight=0.0,
                reasoning=f"Inventory: Could add {item['type']} scroll to belt (inv→belt not implemented)"
            )

        # No urgent refill needs
        return None
