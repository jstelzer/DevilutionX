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

        Urgency Levels:
        1. EMERGENCY (HP<30% + no belt HP): weight 0.95 (beats almost everything)
        2. PROACTIVE (no belt HP + safe): weight 0.7 (beats movement/combat)
        3. NORMAL (belt_hp < 4): weight 0.4 (original behavior)

        Priority by item type:
        1. Health potions (hp, rj) → fill belt slots
        2. Mana potions (mp) → fill belt slots (if caster)
        3. Healing scrolls (sh) → backup for health
        4. Other scrolls → utility slots
        """
        belt = state.get("belt", [])
        inventory = state.get("inventory", [])
        stats = state.get("stats", {})
        me = state.get("me", [0, 0, 100, 100])
        hp_pct = me[2]

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
        belt_mp = sum(1 for slot in belt if slot == "mp")

        # Detect urgency level
        is_emergency = hp_pct < 30 and belt_hp == 0  # Low HP + no belt potions
        is_proactive = belt_hp == 0  # Empty belt (should refill before danger)

        # Priority 1: Fill belt with health potions (want 4-6 slots)
        if belt_hp < 4 and hp_items:
            item = hp_items[0]
            belt_slot = empty_belt_slots[0]

            # Determine urgency weight
            if is_emergency:
                weight = 0.95  # CRITICAL: beats almost everything except healing with potions
                reasoning = "Inventory: EMERGENCY belt refill - low HP + empty belt"
                logger.warning(f"🚨 {reasoning}: {item['type']} → belt slot {belt_slot}")
            elif is_proactive:
                weight = 0.7   # HIGH: beats movement/combat to prevent emergencies
                reasoning = "Inventory: Proactive belt refill - empty belt"
                logger.info(f"⚠️ {reasoning}: {item['type']} → belt slot {belt_slot}")
            else:
                weight = 0.4   # NORMAL: top up belt (belt_hp < 4)
                reasoning = f"Inventory: Refilling belt with {item['type']}"
                logger.info(f"Inventory: Moving {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return AgentResponse(
                command=f"BELT {item['slot']} {belt_slot}",
                weight=weight,
                reasoning=reasoning
            )

        # Priority 2: Fill belt with mana potions (casters only, want 2-3 slots)
        player_class = stats.get("class", 0)
        if player_class == 2 and belt_mp < 2 and mp_items:  # Sorcerer
            item = mp_items[0]
            belt_slot = empty_belt_slots[0]

            # Casters need mana for combat effectiveness
            mp_pct = me[3]
            is_emergency_mp = mp_pct < 20 and belt_mp == 0
            is_proactive_mp = belt_mp == 0

            if is_emergency_mp:
                weight = 0.85  # HIGH: caster without mana can't fight effectively
                reasoning = "Inventory: EMERGENCY mana refill - low MP + empty belt"
                logger.warning(f"🚨 {reasoning}: {item['type']} → belt slot {belt_slot}")
            elif is_proactive_mp:
                weight = 0.65  # MEDIUM-HIGH: refill before running out
                reasoning = "Inventory: Proactive mana refill - empty belt"
                logger.info(f"⚠️ {reasoning}: {item['type']} → belt slot {belt_slot}")
            else:
                weight = 0.4   # NORMAL: top up mana
                reasoning = f"Inventory: Refilling belt with {item['type']}"
                logger.info(f"Inventory: Moving {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return AgentResponse(
                command=f"BELT {item['slot']} {belt_slot}",
                weight=weight,
                reasoning=reasoning
            )

        # Priority 3: Add healing scrolls as backup (if no HP potions available)
        if belt_hp < 2 and heal_scrolls:
            item = heal_scrolls[0]
            belt_slot = empty_belt_slots[0]

            # If low HP and no potions, healing scrolls become urgent
            if hp_pct < 40 and belt_hp == 0 and not hp_items:
                weight = 0.8   # URGENT: last resort for healing
                reasoning = "Inventory: URGENT healing scroll refill - low HP, no potions"
                logger.warning(f"🚨 {reasoning}: {item['type']} → belt slot {belt_slot}")
            else:
                weight = 0.3   # NORMAL: add scrolls as backup
                reasoning = f"Inventory: Refilling belt with {item['type']} scroll"
                logger.info(f"Inventory: Moving {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return AgentResponse(
                command=f"BELT {item['slot']} {belt_slot}",
                weight=weight,
                reasoning=reasoning
            )

        # Priority 4: Add town portal scrolls for convenience
        if len(empty_belt_slots) >= 2 and portal_scrolls:
            item = portal_scrolls[0]
            belt_slot = empty_belt_slots[0]

            logger.info(f"Inventory: Moving {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return AgentResponse(
                command=f"BELT {item['slot']} {belt_slot}",
                weight=0.2,  # Lowest priority
                reasoning=f"Inventory: Adding {item['type']} scroll to belt"
            )

        # No urgent refill needs
        return None
