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
        npcs = state.get("npcs", [])
        me = state.get("me", [0, 0, 100, 100])
        has_stores = len(stores) > 0

        # Debug logging - show NPCs and distance to Pepin
        pepin = next((npc for npc in npcs if npc["type"] == "hl"), None)
        if pepin:
            dist = abs(pepin["x"] - me[0]) + abs(pepin["y"] - me[1])
            logger.info(f"🛒 Shopping: dist_to_pepin={dist}, stores={list(stores.keys())}, pepin_pos=({pepin['x']},{pepin['y']}), me_pos=({me[0]},{me[1]})")
        else:
            logger.warning(f"🛒 Shopping: Pepin not found in NPCs, stores={list(stores.keys())}")

        # Warning if stores empty
        if state.get("in_town") and not has_stores:
            logger.warning(f"🛒 Shopping should_activate: in_town=True but stores={stores}")

        return has_stores

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Evaluate shopping needs and recommend action.

        Priority:
        1. Buy health potions if belt has < 3 AND inventory doesn't have them
        2. Sell junk items if inventory > 80% full (deferred to Griswold agent)
        3. Repair damaged equipment (future)
        """
        belt = state.get("belt", [])
        inventory = state.get("inventory", [])
        stores = state.get("stores", {})
        gold = state.get("gold", 0)

        # Count available health potions in belt AND inventory
        hp_potions_belt = sum(1 for slot in belt if slot == "hp")
        hp_potions_inv = sum(1 for item in inventory if item["type"] == "hp")
        hp_potions = hp_potions_belt + hp_potions_inv

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
HP Potions in belt: {hp_potions_belt}
HP Potions in inventory: {hp_potions_inv}
Total HP Potions: {hp_potions}
Healer inventory: {len(healer_items)} items
HP Potion available: {item['price']} gold
Our gold: {gold}

We need more health potions (have {hp_potions} total, want 4+).

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
                    parsed.reasoning = f"Shopping: Buy health potion ({item['price']}g, have {gold}g)"
                    logger.info(f"Shopping: Recommending BUY hl {item['id']} (price={item['price']}, gold={gold}, belt_hp={hp_potions})")
                    return parsed
                else:
                    logger.warning(f"Shopping: Failed to parse BUY command from LLM: {response}")

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

        # Log why we're not buying potions
        if hp_potions >= 4:
            logger.debug(f"Shopping: Have {hp_potions} HP potions (belt={hp_potions_belt}, inv={hp_potions_inv}), no need to buy")

        # Check for gear upgrades at Griswold's shop
        if "sm" in stores and self.profile:
            smith_items = stores["sm"]
            equipped = state.get("equipped", {})

            # Look for weapons/armor that are upgrades
            for item in smith_items:
                item_type = item["type"]
                item_quality = item["quality"]
                item_price = item["price"]

                # Skip if we can't afford it
                if gold < item_price:
                    continue

                # Use profile to check if we want this type of item
                eval = self.profile.should_keep_item(item_type, item_quality)

                # Skip if profile says we don't want this item type
                if not eval["keep"] or eval["priority"] < 0.5:
                    continue

                # Determine which slot this item goes in
                slot = self._get_equipment_slot(item_type)
                if not slot:
                    continue

                # Check if we have something equipped in that slot
                equipped_item = equipped.get(slot)

                # If slot is empty, or we only have normal quality and this is magic/unique
                should_buy = False
                if not equipped_item:
                    should_buy = True  # Empty slot - buy it
                elif equipped_item["quality"] == "normal" and item_quality in ["magic", "unique"]:
                    should_buy = True  # Upgrade from normal to magic/unique
                elif equipped_item["quality"] == "magic" and item_quality == "unique":
                    should_buy = True  # Upgrade from magic to unique

                if should_buy:
                    prompt = f"""You are the Shopping specialist. Decide if we should buy this gear upgrade.

Item: {item_type} ({item_quality})
Price: {item_price} gold
Our gold: {gold}
Currently equipped: {equipped_item['type'] if equipped_item else 'nothing'} ({equipped_item['quality'] if equipped_item else 'empty'})
Character: {self.profile.class_name} - {eval['reason']}

This is a good upgrade - buy it!

Output ONE line only:
BUY sm {item['id']} <weight>

Weight (0.0-1.0):
- 0.9 = Unique item upgrade
- 0.7 = Magic item upgrade
- 0.5 = Filling empty slot
- 0.0 = Don't buy

Example: BUY sm {item['id']} 0.7"""

                    response = self.query_llm(prompt, grammar=SHOPPING_GRAMMAR)

                    parsed = self.parse_weighted_response(response)
                    if parsed and parsed.command.startswith("BUY"):
                        parsed.reasoning = f"Shopping: Buy {item_type} upgrade ({item_price}g, {item_quality})"
                        logger.info(f"Shopping: Recommending BUY sm {item['id']} ({item_type} {item_quality}, {item_price}g)")
                        return parsed

        # No shopping needs right now
        return None

    def _get_equipment_slot(self, item_type: str) -> str:
        """Map item type to equipment slot"""
        slot_map = {
            # Weapons
            "sw": "hand_left",
            "ax": "hand_left",
            "bw": "hand_left",
            "mc": "hand_left",
            "st": "hand_left",
            # Armor
            "la": "chest",
            "ma": "chest",
            "ha": "chest",
            # Accessories
            "hl": "head",
            "sh": "hand_right",  # Shield
            "rg": "ring_left",   # Ring (could be either)
            "am": "amulet",
        }
        return slot_map.get(item_type, "")
