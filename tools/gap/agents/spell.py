"""
Spell Casting Agent - ranged magic attacks, driven by the engine's spell menu.

The agent does NOT hard-code spell ids, names, mana costs, or ranges — those are
the engine's metadata and live in the DSL's KS= list (id, name, level, mana cost,
flags: offensive/town/affordable). The old hard-coded tables drifted from the
engine (e.g. id 2 is Healing, not Firebolt) and silently broke casting. All that
remains here is *tactics*: which known, affordable, offensive spell to prefer for
the situation — referenced by the engine-provided name, never a magic number.
"""

import logging
import math
from typing import Dict, Any, Optional, List, Tuple

from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# Tactics only (not engine data): spells worth aiming at a cluster, matched by the
# engine's name (lower-cased). Everything else is treated as single-target.
AOE_SPELL_NAMES = {
    "fireball", "nova", "chain lightning", "flame wave",
    "lightning wall", "apocalypse", "inferno",
}
# A single generous cast range; the engine doesn't publish per-spell range and
# most attack spells reach ~15 tiles. This is a behavior knob, not engine data.
MAX_CAST_RANGE = 15


class SpellAgent(BaseAgent):
    """Selects and casts the best known offensive spell for the situation."""

    def __init__(self, **kwargs):
        super().__init__(name="Spell", **kwargs)
        self.use_memory_context = False  # keep the tactical loop terse and fast
        self.last_cast_tick = 0
        # Ticks between casts. Kept short so a caster keeps casting rather than
        # leaving gaps for CombatAgent to fill with melee; the engine's own cast
        # animation gates the real rate, so this is just light anti-spam.
        self.cast_cooldown = 5
        self.last_staff_charges = None  # detect when staff charges hit zero

    def should_activate(self, state: Dict[str, Any]) -> bool:
        if state.get("in_town"):
            return False
        if not state.get("mobs"):
            return False
        tick = state.get("tick", 0)
        if (tick - self.last_cast_tick) < self.cast_cooldown:
            return False
        # Active if she can attack at range at all: a known offensive spell (the
        # engine already told us what she knows) or a charged staff. No magic-stat
        # guess — knowing an offensive spell IS the qualification, so a Warrior who
        # pumped Magic and learned Firebolt casts it too.
        return self._has_offensive_spell(state) or self._has_staff_charges(state)

    def _has_offensive_spell(self, state: Dict[str, Any]) -> bool:
        return any(s.get("offensive") for s in state.get("spells", []))

    def _has_staff_charges(self, state: Dict[str, Any]) -> bool:
        """True if a charged staff is equipped (casts at range, no mana cost)."""
        staff = (state.get("equipped", {}) or {}).get("hand_left") or {}
        return staff.get("type") == "st" and staff.get("charges", 0) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        monsters = state.get("mobs", [])
        if not monsters:
            return None

        me = state.get("me", [0, 0, 100, 100])
        my_pos = (me[0], me[1]) if len(me) >= 2 else (0, 0)
        mana_pct = me[3] if len(me) > 3 else 100

        class_context = ""
        if self.profile:
            class_context = f"{self.profile.class_name} " if not self.profile.is_caster else ""

        # Staff with charges: track it, and announce when it runs dry.
        staff = (state.get("equipped", {}) or {}).get("hand_left") or {}
        staff_charges = staff.get("charges", 0) if staff.get("type") == "st" else 0
        if staff.get("type") == "st":
            if self.last_staff_charges and self.last_staff_charges > 0 and staff_charges == 0:
                self.last_staff_charges = staff_charges
                return AgentResponse(
                    command="SAY My staff is out of charges — time for a new one or a recharge at Adria.",
                    weight=0.1,
                    reasoning="Spell: staff depleted notification",
                )
            self.last_staff_charges = staff_charges

        spell_id, target_pos, weight, reasoning = self._select_spell(
            monsters, my_pos, mana_pct, class_context,
            staff.get("spell_id") if staff_charges > 0 else None,
            staff_charges, state.get("spells", []),
        )
        if spell_id is None:
            # Nothing castable right now. If it's only because the nearest enemy is
            # out of cast range, CLOSE on it to get within range — a caster should
            # advance to blast, not idle (which let belt-fiddling/movement win and
            # made her look passive). Cast-kite: move toward, then fire when in range.
            return self._approach_to_cast(monsters, my_pos)

        self.last_cast_tick = state.get("tick", 0)
        return AgentResponse(
            command=f"CAST {spell_id} {target_pos[0]} {target_pos[1]}",
            weight=weight,
            reasoning=reasoning,
        )

    def _approach_to_cast(self, monsters, my_pos):
        """Move toward the nearest monster to get within cast range. Returns a MV
        AgentResponse, or None if there's no monster worth approaching."""
        nearest = None
        nd = 999.0
        for mob in monsters:
            d = math.hypot(mob.get("x", 0) - my_pos[0], mob.get("y", 0) - my_pos[1])
            if d < nd:
                nd = d
                nearest = mob
        # Already in range (handled by _select_spell) or no one to chase across
        # the whole level — don't.
        if nearest is None or nd <= MAX_CAST_RANGE or nd > 40:
            return None
        return AgentResponse(
            command=f"MV {nearest.get('x', 0)} {nearest.get('y', 0)}",
            weight=0.7,  # beats belt-fiddle (~0.3) and damped caster-melee
            reasoning=f"Spell: closing to cast range on monster at {nd:.0f} tiles",
        )

    def _select_spell(
        self,
        monsters: list,
        my_pos: Tuple[int, int],
        mana_pct: int,
        class_context: str,
        staff_spell_id: Optional[int],
        staff_charges: int,
        spells: List[Dict[str, Any]],
    ) -> Tuple[Optional[int], Optional[Tuple[int, int]], float, str]:
        """Pick a spell for the current situation. Returns (id, target, weight, why)."""
        # Find the best single target and any close-together cluster. Target ANY
        # visible monster — the DSL only lists monsters in light radius / line of
        # sight, so they're all valid enemies. We deliberately do NOT require the
        # `hostile` flag (bit 0): that's only set when goal==Attack, so a monster
        # still approaching — or one locked onto the human — reads as non-hostile
        # and used to give "No valid targets," leaving the caster to melee.
        best_target = None
        min_distance = 999.0
        attacking_count = 0
        grouped = 0

        for mob in monsters:
            if mob.get("flags", 0) & 1:  # actively attacking (a hint, not a gate)
                attacking_count += 1
            mob_pos = (mob.get("x", 0), mob.get("y", 0))
            distance = math.hypot(mob_pos[0] - my_pos[0], mob_pos[1] - my_pos[1])
            if distance <= 10:
                grouped += 1
            if distance < min_distance:
                min_distance = distance
                best_target = {"pos": mob_pos, "distance": distance, "hp": mob.get("hp%", 100)}

        if not best_target:
            return None, None, 0.0, "No valid targets"
        if best_target["distance"] > MAX_CAST_RANGE:
            return None, None, 0.0, f"Target {best_target['distance']:.1f} > cast range {MAX_CAST_RANGE}"

        target_pos = best_target["pos"]
        is_group = grouped >= 3

        # PRIORITY 1: spend staff charges when mana is low (saves mana for free
        # ranged damage). We don't know the staff spell's name (it's not in KS),
        # so it's treated as single-target here.
        if staff_spell_id and staff_charges > 0 and mana_pct < 40:
            return staff_spell_id, target_pos, 0.85, \
                f"{class_context}Staff spell (charges: {staff_charges}, saving mana)"

        # PRIORITY 2: cast a known, affordable, offensive spell from the engine menu.
        castable = [s for s in spells if s.get("offensive") and s.get("affordable")]
        pick = None
        if is_group:
            aoe = [s for s in castable if s["name"].lower() in AOE_SPELL_NAMES]
            if aoe:
                pick = max(aoe, key=lambda s: s["mana"])  # strongest AoE we can afford
        if pick is None and castable:
            # Strongest single option ~ most expensive affordable spell.
            pick = max(castable, key=lambda s: s["mana"])

        if pick is not None:
            is_aoe = pick["name"].lower() in AOE_SPELL_NAMES
            weight = 0.9 if (is_group and is_aoe) else 0.8
            tgt = f"group of {grouped}" if (is_group and is_aoe) else f"{best_target['distance']:.1f} tiles"
            if attacking_count >= 4:
                weight += 0.1
            if best_target["hp"] <= 30:
                weight += 0.05
            return pick["id"], target_pos, weight, \
                f"{class_context}Spell: {pick['name']} ({tgt}, mana {mana_pct}%)"

        # PRIORITY 3: nothing affordable to cast, but the staff still has charges.
        if staff_spell_id and staff_charges > 0:
            return staff_spell_id, target_pos, 0.85, \
                f"{class_context}Staff spell (no affordable known spell, charges: {staff_charges})"

        return None, None, 0.0, "Conserving (no known affordable spell, no staff charges)"


# Export for agent system
__all__ = ['SpellAgent']
