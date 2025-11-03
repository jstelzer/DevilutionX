"""
Spell Casting Agent - Ranged magic attacks for sorcerer/mage classes
"""

import logging
from typing import Dict, Any, Optional, Tuple
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# Spell ID constants (from Source/spelldat.h)
SPELL_FIREBOLT = 2
SPELL_CHARGED_BOLT = 3
SPELL_FIREBALL = 15
SPELL_LIGHTNING = 16
SPELL_FLASH = 17
SPELL_FIRE_WALL = 20
SPELL_STONE_CURSE = 24
SPELL_CHAIN_LIGHTNING = 26

# Mana costs (approximate - actual costs vary by spell level)
MANA_COSTS = {
    SPELL_FIREBOLT: 6,
    SPELL_CHARGED_BOLT: 6,
    SPELL_FIREBALL: 16,
    SPELL_LIGHTNING: 10,
    SPELL_FLASH: 30,
    SPELL_FIRE_WALL: 28,
    SPELL_STONE_CURSE: 60,
    SPELL_CHAIN_LIGHTNING: 30,
}

# Spell ranges (tiles)
SPELL_RANGES = {
    SPELL_FIREBOLT: 15,
    SPELL_CHARGED_BOLT: 15,
    SPELL_FIREBALL: 15,
    SPELL_LIGHTNING: 15,
    SPELL_FLASH: 8,
    SPELL_FIRE_WALL: 10,
    SPELL_STONE_CURSE: 15,
    SPELL_CHAIN_LIGHTNING: 15,
}


class SpellAgent(BaseAgent):
    """Specialist for spell casting combat"""

    def __init__(self, **kwargs):
        super().__init__(name="Spell", priority=9, **kwargs)  # High priority, just below healing
        self.last_cast_tick = 0
        self.cast_cooldown = 20  # Ticks between casts (prevent spam)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Activate if we have monsters, mana, and sufficient magic stat"""
        # Stat-based activation: any class can cast if Magic >= 20
        # (Warriors can learn Town Portal, Healing, etc. at higher levels)
        stats = state.get("stats", {})
        magic_stat = stats.get("mag", 0)

        if magic_stat < 20:  # Insufficient magic to cast effectively
            return False

        # Need mana
        me = state.get("me", {})
        mana_pct = me.get("mp%", 0)
        if mana_pct < 20:  # Save mana for emergencies
            return False

        # Need monsters in range
        monsters = state.get("monsters", [])
        if not monsters:
            return False

        # In town = no casting
        if state.get("in_town"):
            return False

        # Cooldown check
        tick = state.get("tick", 0)
        if tick - self.last_cast_tick < self.cast_cooldown:
            return False

        return True

    def decide(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """Select and cast appropriate spell"""
        monsters = state.get("monsters", [])
        if not monsters:
            return None

        me = state.get("me", {})
        my_pos = (me.get("x", 0), me.get("y", 0))
        mana_pct = me.get("mp%", 100)
        stats = state.get("stats", {})
        magic_stat = stats.get("mag", 0)

        # Get class context from profile if available
        class_context = ""
        if self.profile:
            class_context = f"{self.profile.class_name} " if not self.profile.is_caster else ""

        # Select spell and target based on situation
        spell_id, target_pos, weight, reasoning = self._select_spell(
            monsters, my_pos, mana_pct, magic_stat, class_context
        )

        if spell_id is None:
            return None

        # Build CAST command
        command = f"CAST {spell_id} {target_pos[0]} {target_pos[1]}"

        # Update last cast tick
        self.last_cast_tick = state.get("tick", 0)

        return AgentResponse(
            command=command,
            weight=weight,
            reasoning=reasoning
        )

    def _select_spell(
        self,
        monsters: list,
        my_pos: Tuple[int, int],
        mana_pct: int,
        magic_stat: int,
        class_context: str = ""
    ) -> Tuple[Optional[int], Optional[Tuple[int, int]], float, str]:
        """
        Select best spell for current situation.

        Args:
            class_context: Optional class prefix for logging (e.g., "Warrior ")

        Returns: (spell_id, target_pos, weight, reasoning)
        """
        import math

        # Calculate distances and find best target
        best_target = None
        min_distance = 999
        hostile_count = 0
        grouped_monsters = []  # Monsters close together

        for mob in monsters:
            mob_pos = (mob.get("x", 0), mob.get("y", 0))
            mob_hp = mob.get("hp%", 100)
            mob_flags = mob.get("flags", 0)

            dx = mob_pos[0] - my_pos[0]
            dy = mob_pos[1] - my_pos[1]
            distance = math.sqrt(dx * dx + dy * dy)

            # Count hostile monsters
            if mob_flags & 1:  # Hostile flag
                hostile_count += 1

            # Track best single target (closest, hostile, low HP)
            if mob_flags & 1 and distance < min_distance:
                min_distance = distance
                best_target = {
                    "mob": mob,
                    "pos": mob_pos,
                    "distance": distance,
                    "hp": mob_hp
                }

            # Check for grouped monsters (for AoE spells)
            if mob_flags & 1 and distance <= 10:
                grouped_monsters.append((mob, mob_pos, distance))

        if not best_target:
            return None, None, 0.0, "No valid targets"

        # Spell selection logic based on situation
        spell_id = None
        target_pos = best_target["pos"]
        weight = 0.7  # Base weight
        reasoning = ""

        # High mana + grouped enemies = Fireball (AoE)
        if mana_pct >= 40 and len(grouped_monsters) >= 3:
            spell_id = SPELL_FIREBALL
            weight = 0.9  # High priority for grouped targets
            reasoning = f"{class_context}Spell: Fireball on group of {len(grouped_monsters)}"

        # Mid-range combat with decent mana = Lightning (fast projectile)
        elif mana_pct >= 30 and best_target["distance"] <= 12:
            spell_id = SPELL_LIGHTNING
            weight = 0.8
            reasoning = f"{class_context}Spell: Lightning at {best_target['distance']:.1f} tiles"

        # Low mana or long range = Firebolt (cheap, long range)
        elif mana_pct >= 20:
            spell_id = SPELL_FIREBOLT
            weight = 0.7
            reasoning = f"{class_context}Spell: Firebolt (mana: {mana_pct}%)"

        # Very low mana = conserve, don't cast
        else:
            return None, None, 0.0, "Conserving mana"

        # Safety check: ensure spell in range
        spell_range = SPELL_RANGES.get(spell_id, 15)
        if best_target["distance"] > spell_range:
            # Too far - move closer instead
            return None, None, 0.0, f"Target {best_target['distance']:.1f} > range {spell_range}"

        # Boost weight for dangerous situations
        if hostile_count >= 4:
            weight += 0.1  # Multiple threats
        if best_target["hp"] <= 30:
            weight += 0.05  # Almost dead target

        return spell_id, target_pos, weight, reasoning


# Export for agent system
__all__ = ['SpellAgent']
