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
        super().__init__(name="Spell", **kwargs)
        self.last_cast_tick = 0
        self.cast_cooldown = 20  # Ticks between casts (prevent spam)
        self.last_staff_charges = None  # Track staff charges to detect when they hit zero

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Activate if we have monsters, mana, and sufficient magic stat"""
        # Stat-based activation: any class can cast if Magic >= 20
        # (Warriors can learn Town Portal, Healing, etc. at higher levels)
        stats = state.get("stats", {})
        magic_stat = stats.get("mag", 0)

        if magic_stat < 20:  # Insufficient magic to cast effectively
            return False

        # Need mana
        me = state.get("me", [0, 0, 100, 100])
        mana_pct = me[3] if len(me) > 3 else 100
        if mana_pct < 20:  # Save mana for emergencies
            return False

        # Need monsters in range
        monsters = state.get("mobs", [])
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

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """Select and cast appropriate spell"""
        monsters = state.get("mobs", [])
        if not monsters:
            return None

        me = state.get("me", [0, 0, 100, 100])
        my_pos = (me[0], me[1]) if len(me) >= 2 else (0, 0)
        mana_pct = me[3] if len(me) > 3 else 100
        stats = state.get("stats", {})
        magic_stat = stats.get("mag", 0)
        equipped = state.get("equipped", {})

        # Get class context from profile if available
        class_context = ""
        if self.profile:
            class_context = f"{self.profile.class_name} " if not self.profile.is_caster else ""

        # Check if we have a staff with charges equipped
        hand_left = equipped.get("hand_left")
        staff_spell_id = None
        staff_charges = 0
        if hand_left and hand_left.get("type") == "st":
            staff_charges = hand_left.get("charges", 0)
            staff_spell_id = hand_left.get("spell_id")

            # Detect when staff charges hit zero
            if self.last_staff_charges is not None and self.last_staff_charges > 0 and staff_charges == 0:
                # Staff just ran out - notify via chat
                spell_names = {
                    SPELL_FIREBOLT: "Firebolt",
                    SPELL_CHARGED_BOLT: "Charged Bolt",
                    SPELL_FIREBALL: "Fireball",
                    SPELL_LIGHTNING: "Lightning",
                    SPELL_FLASH: "Flash",
                    SPELL_FIRE_WALL: "Fire Wall",
                    SPELL_STONE_CURSE: "Stone Curse",
                    SPELL_CHAIN_LIGHTNING: "Chain Lightning",
                }
                spell_name = spell_names.get(staff_spell_id, f"spell {staff_spell_id}")

                chat_msg = f"My staff of {spell_name} is out of charges. Time to find a new one or visit Adria for a recharge."
                logger.info(f"⚡ Staff depleted: {chat_msg}")

                # Return a SAY command to notify the player
                return AgentResponse(
                    command=f"SAY {chat_msg}",
                    weight=0.1,  # Low priority, just informational
                    reasoning=f"Staff depleted notification"
                )

            # Track current charges for next tick
            self.last_staff_charges = staff_charges

        # Select spell and target based on situation
        spell_id, target_pos, weight, reasoning = self._select_spell(
            monsters, my_pos, mana_pct, magic_stat, class_context,
            staff_spell_id, staff_charges
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
        class_context: str = "",
        staff_spell_id: Optional[int] = None,
        staff_charges: int = 0
    ) -> Tuple[Optional[int], Optional[Tuple[int, int]], float, str]:
        """
        Select best spell for current situation.

        Args:
            class_context: Optional class prefix for logging (e.g., "Warrior ")
            staff_spell_id: Spell ID available on equipped staff (if any)
            staff_charges: Number of charges remaining on staff

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
        use_staff = False

        # PRIORITY 1: Use staff charges if available (no mana cost!)
        # Staff charges are precious - prefer them when mana is low
        if staff_spell_id and staff_charges > 0:
            # Only use staff if mana is below 40% OR staff spell matches our preferred spell
            if mana_pct < 40:
                spell_id = staff_spell_id
                weight = 0.85  # High priority - saves mana
                reasoning = f"{class_context}Staff spell (charges: {staff_charges}, saving mana)"
                use_staff = True
            # Also prefer staff for grouped enemies if it's Fireball/Lightning/Chain Lightning
            elif staff_spell_id in [SPELL_FIREBALL, SPELL_LIGHTNING, SPELL_CHAIN_LIGHTNING] and len(grouped_monsters) >= 3:
                spell_id = staff_spell_id
                weight = 0.9
                reasoning = f"{class_context}Staff AoE spell (charges: {staff_charges})"
                use_staff = True

        # PRIORITY 2: Use memorized spells if staff not used
        if not use_staff:
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

            # Very low mana BUT we have staff charges = use staff!
            elif staff_spell_id and staff_charges > 0:
                spell_id = staff_spell_id
                weight = 0.85
                reasoning = f"{class_context}Staff spell (LOW MANA, charges: {staff_charges})"
                use_staff = True

            # Very low mana and no staff = conserve
            else:
                return None, None, 0.0, "Conserving mana (no staff charges)"

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
