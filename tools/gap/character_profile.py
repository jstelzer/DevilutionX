"""
Character Profile - Self-awareness and identity for GAP agents

Provides context about class, role, playstyle, and preferences.
Initialized during handshake and cached throughout session.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class CharacterProfile:
    """
    Character identity and role awareness.

    Cached on handshake, updated on level changes.
    Provides context for agent decisions and chat responses.
    """

    # Class metadata
    CLASS_NAMES = ["Warrior", "Rogue", "Sorcerer", "Monk", "Bard", "Barbarian"]

    PLAYSTYLES = {
        0: "melee_tank",      # Warrior
        1: "ranged_dps",      # Rogue
        2: "caster_dps",      # Sorcerer
        3: "melee_hybrid",    # Monk
        4: "support_hybrid",  # Bard
        5: "melee_berserker", # Barbarian
    }

    ROLE_DESCRIPTIONS = {
        0: "Frontline tank - high HP, melee damage, shield blocking",
        1: "Ranged DPS - high DEX, bow damage, hit-and-run tactics",
        2: "Caster DPS - high MAG, spell damage, mana management",
        3: "Melee hybrid - balanced stats, martial arts, magic support",
        4: "Support hybrid - buffs, debuffs, item identification",
        5: "Melee berserker - very high damage, rage mechanics, glass cannon",
    }

    PREFERRED_WEAPONS = {
        0: ["sw", "ax", "mc"],  # Warrior: swords, axes, maces
        1: ["bw"],              # Rogue: bows
        2: ["st"],              # Sorcerer: staffs
        3: ["st", "sw"],        # Monk: staffs, swords
        4: ["sw", "st"],        # Bard: swords, staffs
        5: ["ax", "sw"],        # Barbarian: axes, swords
    }

    PREFERRED_ARMOR = {
        0: ["ha", "ma"],  # Warrior: heavy/medium armor
        1: ["la"],        # Rogue: light armor (mobility)
        2: ["la"],        # Sorcerer: light armor (casting)
        3: ["la", "ma"],  # Monk: light/medium armor
        4: ["la", "ma"],  # Bard: light/medium armor
        5: ["ma", "ha"],  # Barbarian: medium/heavy armor
    }

    def __init__(self, initial_state: Dict[str, Any]):
        """
        Initialize character profile from first state snapshot.

        Args:
            initial_state: Parsed DSL state from handshake
        """
        stats = initial_state.get("stats", {})

        self.class_id = stats.get("class", 0)
        self.class_name = self.CLASS_NAMES[self.class_id] if self.class_id < len(self.CLASS_NAMES) else "Unknown"
        self.level = stats.get("lvl", 1)
        self.experience = stats.get("exp", 0)

        # Base stats
        self.strength = stats.get("str", 0)
        self.dexterity = stats.get("dex", 0)
        self.magic = stats.get("mag", 0)
        self.vitality = stats.get("vit", 0)
        self.stat_points = stats.get("pts", 0)

        # Role metadata
        self.playstyle = self.PLAYSTYLES.get(self.class_id, "unknown")
        self.role_description = self.ROLE_DESCRIPTIONS.get(self.class_id, "Unknown class")
        self.preferred_weapons = self.PREFERRED_WEAPONS.get(self.class_id, [])
        self.preferred_armor = self.PREFERRED_ARMOR.get(self.class_id, [])

        # Derived traits
        self.is_caster = self.class_id in [2]  # Sorcerer
        self.is_melee = self.class_id in [0, 3, 5]  # Warrior, Monk, Barbarian
        self.is_ranged = self.class_id in [1]  # Rogue
        self.can_use_shields = self.class_id in [0, 3]  # Warrior, Monk

        # Inventory snapshot (updated separately)
        self.inventory_count = initial_state.get("inv_count", 0)
        self.belt_summary = self._summarize_belt(initial_state.get("belt", []))

        logger.info("👤 Character Profile Created")
        logger.info(f"   Class: {self.class_name} (level {self.level})")
        logger.info(f"   Role: {self.role_description}")
        logger.info(f"   Playstyle: {self.playstyle}")
        logger.info(f"   Stats: STR={self.strength} DEX={self.dexterity} MAG={self.magic} VIT={self.vitality}")
        logger.info(f"   Preferred weapons: {', '.join(self.preferred_weapons)}")
        logger.info(f"   Preferred armor: {', '.join(self.preferred_armor)}")

    def _summarize_belt(self, belt: List[str]) -> str:
        """Create human-readable belt summary"""
        hp_count = sum(1 for slot in belt if slot == "hp")
        mp_count = sum(1 for slot in belt if slot == "mp")
        scroll_count = sum(1 for slot in belt if slot.startswith("s") and slot != "em")

        return f"{hp_count} HP, {mp_count} MP, {scroll_count} scrolls"

    def update_stats(self, state: Dict[str, Any]) -> bool:
        """
        Update profile from new state (check for level ups, etc.)

        Returns:
            True if significant changes occurred (level up, stat changes)
        """
        stats = state.get("stats", {})
        current_level = stats.get("lvl", self.level)

        changed = False

        # Check for level up
        if current_level > self.level:
            logger.info(f"🎉 LEVEL UP! {self.class_name} {self.level} → {current_level}")
            self.level = current_level
            changed = True

        # Update stats
        self.strength = stats.get("str", self.strength)
        self.dexterity = stats.get("dex", self.dexterity)
        self.magic = stats.get("mag", self.magic)
        self.vitality = stats.get("vit", self.vitality)
        self.stat_points = stats.get("pts", self.stat_points)
        self.experience = stats.get("exp", self.experience)

        # Update inventory summary
        self.inventory_count = state.get("inv_count", self.inventory_count)
        self.belt_summary = self._summarize_belt(state.get("belt", []))

        return changed

    def should_keep_item(self, item_type: str, item_quality: str) -> Dict[str, Any]:
        """
        Evaluate if item matches character's role.

        Args:
            item_type: Item type code (sw, ax, bw, etc.)
            item_quality: "normal", "magic", or "unique"

        Returns:
            {
                "keep": bool,
                "reason": str,
                "priority": float  # 0.0-1.0
            }
        """
        # Always keep magic/unique items (might be valuable to sell or use)
        if item_quality in ["magic", "unique"]:
            return {
                "keep": True,
                "reason": f"{item_quality.capitalize()} items are valuable",
                "priority": 0.8
            }

        # Check weapon preference
        if item_type in self.preferred_weapons:
            return {
                "keep": True,
                "reason": f"I'm a {self.class_name} - {item_type} is my preferred weapon",
                "priority": 0.9
            }

        # Check armor preference
        if item_type in self.preferred_armor:
            return {
                "keep": True,
                "reason": f"I'm a {self.class_name} - {item_type} is suitable armor for me",
                "priority": 0.7
            }

        # Wrong weapon type for class
        if item_type in ["sw", "ax", "bw", "mc", "st"] and item_type not in self.preferred_weapons:
            return {
                "keep": False,
                "reason": f"I'm a {self.class_name} - {item_type} isn't my style (prefer {', '.join(self.preferred_weapons)})",
                "priority": 0.2
            }

        # Wrong armor type
        if item_type in ["la", "ma", "ha"] and item_type not in self.preferred_armor:
            return {
                "keep": False,
                "reason": f"Wrong armor type for {self.class_name} (need {', '.join(self.preferred_armor)})",
                "priority": 0.3
            }

        # Default: keep but low priority
        return {
            "keep": True,
            "reason": "Might be useful or valuable to sell",
            "priority": 0.4
        }

    def get_shopping_priorities(self) -> List[str]:
        """Get prioritized shopping list based on class"""
        if self.is_caster:
            return ["mp", "st", "la", "hp", "sp"]  # Mana, staffs, light armor, healing, portals
        elif self.is_ranged:
            return ["hp", "bw", "la", "sp"]  # Health, bows, light armor, portals
        elif self.is_melee:
            return ["hp", "sw", "ax", "ha", "sh", "sp"]  # Health, weapons, heavy armor, shields, portals
        else:
            return ["hp", "mp", "sp"]  # Generic: health, mana, portals

    def get_chat_context(self) -> str:
        """
        Get character context for chat responses.

        Returns formatted string for injecting into chat prompts.
        """
        return f"""You are {self.class_name} (level {self.level}).
Role: {self.role_description}
Current stats: STR={self.strength} DEX={self.dexterity} MAG={self.magic} VIT={self.vitality}
Inventory: {self.inventory_count}/40 slots
Belt: {self.belt_summary}"""

    def get_combat_style(self) -> str:
        """
        Return combat style classification for tactical decisions.

        Returns:
            "ranged", "melee", or "caster"
        """
        if self.is_ranged:
            return "ranged"
        elif self.is_caster:
            return "caster"
        elif self.is_melee:
            return "melee"
        else:
            # Fallback: analyze stats
            if self.magic > max(self.strength, self.dexterity):
                return "caster"
            elif self.dexterity > self.strength:
                return "ranged"
            else:
                return "melee"

    def get_combat_context(self) -> str:
        """
        Get detailed tactical context for combat decisions.

        Provides class-specific combat guidance for LLM prompts.
        """
        if self.is_ranged:
            return f"RANGED ATTACKER - High DEX bow user, hit-and-run tactics, kite enemies, prioritize archers"
        elif self.is_caster:
            return f"SPELLCASTER - High MAG spell damage, manage mana (current: MP), keep distance from threats"
        elif self.class_id == 0:  # Warrior
            return f"MELEE TANK - High VIT, absorb damage, protect allies, rush threats"
        elif self.class_id == 5:  # Barbarian
            return f"MELEE BERSERKER - High damage output, aggressive tactics, finish low HP enemies"
        else:  # Generic melee/hybrid
            return f"MELEE FIGHTER - Balanced stats, close combat, adapt to threats"

    def __repr__(self):
        return f"<CharacterProfile: {self.class_name} lvl{self.level} ({self.playstyle})>"
