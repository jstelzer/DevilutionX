"""
Inventory Agent - Belt refill and inventory management
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# How much we want each belt item type to STAY on the belt (higher = keep). Used
# to decide what a FULL belt will give up to make room for a needed potion that's
# stranded in the pack. Generic utility scrolls (sr/si/sc/sl/sf) default to 1, so
# they're the first to be bumped; health/mana/heal-scroll/portal are protected.
BELT_KEEP = {"hp": 6, "rj": 6, "mp": 5, "sh": 4, "sp": 2}


def _belt_keep(item_type: str) -> int:
    return BELT_KEEP.get(item_type, 1)


class InventoryAgent(BaseAgent):
    """Specialist for inventory management - refilling belt from inventory"""

    def __init__(self, **kwargs):
        super().__init__(name="Inventory", **kwargs)
        # Give up on items the engine refuses to belt (e.g. a book/oversized item
        # the DSL typed like a scroll). Without this she loops forever issuing the
        # same failing BELT and never does anything else.
        self._unbeltable = set()      # inv slots the engine won't accept on the belt
        self._belt_try_slot = None    # inv slot we keep trying to belt
        self._belt_try_count = 0      # consecutive identical belt attempts

    def _belt_response(self, item, belt_slot, weight, reasoning):
        """Issue a BELT refill, but stop fixating on an item the engine refuses.
        If we pick the same inv slot 3 ticks running (a success would have changed
        the inventory/belt and thus the pick), blacklist it and bail this tick."""
        slot = item["slot"]
        if slot == self._belt_try_slot:
            self._belt_try_count += 1
        else:
            self._belt_try_slot = slot
            self._belt_try_count = 1
        if self._belt_try_count > 3:
            self._unbeltable.add(slot)
            self._belt_try_slot = None
            self._belt_try_count = 0
            logger.warning(f"Inventory: inv slot {slot} ({item['type']}) can't be belted - giving up")
            return None
        return AgentResponse(command=f"BELT {slot} {belt_slot}", weight=weight, reasoning=reasoning)

    def _find_swap(self, state: Dict[str, Any]):
        """Belt is full: pick a stranded pack potion to swap in for the belt's
        weakest (most disposable) item. Returns (want_item, belt_slot, reasoning)
        or None. Pure — no side effects, so should_activate can call it too."""
        belt = state.get("belt", [])
        inventory = state.get("inventory", [])
        stats = state.get("stats") or {}

        def _ok(item):  # skip items the engine has refused to belt
            return item["slot"] not in self._unbeltable
        hp_items = [i for i in inventory if i["type"] in ("hp", "rj") and _ok(i)]
        mp_items = [i for i in inventory if i["type"] == "mp" and _ok(i)]
        belt_hp = sum(1 for s in belt if s in ("hp", "rj"))
        belt_mp = sum(1 for s in belt if s == "mp")

        # What does the belt most need that's sitting in the pack?
        if belt_hp < 3 and hp_items:
            want, label = hp_items[0], "health"
        elif stats.get("class") == 2 and belt_mp < 2 and mp_items:
            want, label = mp_items[0], "mana"
        else:
            return None

        # Bump the belt's lowest-value slot, but only if it's worth LESS than what
        # we're adding (never trade a potion/heal-scroll away for another potion).
        ranked = sorted(((_belt_keep(t), i, t) for i, t in enumerate(belt)),
                        key=lambda x: x[0])
        low_val, low_slot, low_type = ranked[0]
        if low_val >= _belt_keep(want["type"]):
            return None

        reasoning = (f"Inventory: belt full — bumping {low_type} (belt slot {low_slot}) "
                     f"for a {label} potion from the pack")
        return want, low_slot, reasoning

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Activate if:
        1. Belt has empty slots and the pack has consumables to fill them, OR
        2. Belt is FULL but a needed potion is stranded in the pack behind a
           bumpable utility scroll (belt-swap).
        """
        belt = state.get("belt", [])
        inventory = state.get("inventory", [])

        # Check if inventory has consumables (potions/scrolls)
        consumable_types = ["hp", "mp", "rj", "sh", "sp", "sr", "si", "sl", "sf", "sc"]
        has_consumables = any(item["type"] in consumable_types for item in inventory)
        if not has_consumables:
            return False

        if any(slot == "em" for slot in belt):
            return True

        # Belt full → only worth running if a beneficial potion-for-scroll swap exists.
        return self._find_swap(state) is not None

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
            # Belt full — try to bump a low-value utility item for a potion that's
            # stranded in the pack. The C++ BELT command now swaps the occupant
            # back into the pack rather than rejecting an occupied target slot.
            swap = self._find_swap(state)
            if swap is None:
                return None
            want, belt_slot, reasoning = swap
            logger.info(reasoning)
            return self._belt_response(want, belt_slot, 0.45, reasoning)

        # Categorize inventory items
        def _ok(item):  # skip items the engine has refused to belt
            return item["slot"] not in self._unbeltable
        hp_items = [i for i in inventory if i["type"] in ["hp", "rj"] and _ok(i)]
        mp_items = [i for i in inventory if i["type"] == "mp" and _ok(i)]
        heal_scrolls = [i for i in inventory if i["type"] == "sh" and _ok(i)]
        portal_scrolls = [i for i in inventory if i["type"] == "sp" and _ok(i)]

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

            return self._belt_response(item, belt_slot, weight, reasoning)

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

            return self._belt_response(item, belt_slot, weight, reasoning)

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

            return self._belt_response(item, belt_slot, weight, reasoning)

        # Priority 4: Add town portal scrolls for convenience
        if len(empty_belt_slots) >= 2 and portal_scrolls:
            item = portal_scrolls[0]
            belt_slot = empty_belt_slots[0]

            logger.info(f"Inventory: Moving {item['type']} from inv slot {item['slot']} to belt slot {belt_slot}")

            return self._belt_response(item, belt_slot, 0.2,
                                       f"Inventory: Adding {item['type']} scroll to belt")

        # No urgent refill needs
        return None
