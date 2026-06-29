"""
Mana Agent — keep a caster's mana topped up for spellcasting.

The mirror of HealingAgent, but for the blue bar. When a caster is low on mana
and there are monsters to fight, drink a mana potion from the belt so SpellAgent
can keep casting instead of falling back to staff-melee. Nothing else in the
council ever drinks mana potions: ShoppingAgent/AdriaAgent *buy* them and
SpellAgent only *reads* mp% to decide whether to cast — so without this agent a
caster runs dry and then melees forever.
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)

# Casters cast at Magic >= 20 (mirrors SpellAgent's gate). Below that, a
# character isn't really spending mana, so don't waste potions on it.
CASTER_MAGIC_MIN = 20


class ManaAgent(BaseAgent):
    """Specialist for mana management (drinking mana potions for casters)."""

    def __init__(self, **kwargs):
        super().__init__(name="Mana", **kwargs)
        self.use_memory_context = False  # tactical loop: keep it terse/fast

    def _dps_dry(self, state: Dict[str, Any]) -> bool:
        """Knows an offensive spell but can't afford to MANA-cast any right now.
        The KS '$'/affordable flag is mana-only (a charged staff doesn't mask it),
        so this is the 'I want to blast but I'm tapped out' signal — it should pull
        him toward DRINKING, not toward conserving and poking with the staff."""
        offensive = [s for s in state.get("spells", []) if s.get("offensive")]
        return bool(offensive) and not any(s.get("affordable") for s in offensive)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        # Only casters bother with mana potions.
        stats = state.get("stats") or {}
        if stats.get("mag", 0) < CASTER_MAGIC_MIN:
            return False
        # No drinking in town (the shops/refill agents own town behavior).
        if state.get("in_town"):
            return False
        # Only worth a potion when there's something to fight — mana doesn't regen
        # passively, so don't burn potions while wandering.
        if not state.get("mobs"):
            return False
        # Need a mana potion (or a rejuv, which also restores mana) on the belt.
        belt = state.get("belt", [])
        if not any(t in ("mp", "rj") for t in belt):
            return False
        # Drink to stay charged for DPS, or whenever he's too tapped to cast at all.
        me = state.get("me", [0, 0, 100, 100])
        mp_pct = me[3] if len(me) > 3 else 100
        return mp_pct < 60 or self._dps_dry(state)

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        me = state.get("me", [0, 0, 100, 100])
        mp_pct = me[3] if len(me) > 3 else 100
        belt = state.get("belt", [])

        mp_slot = next((i for i, t in enumerate(belt) if t == "mp"), None)
        rj_slot = next((i for i, t in enumerate(belt) if t == "rj"), None)

        # "Charge up to DPS": pots are ammo, not treasure. If he knows an offensive
        # spell but can't afford to cast ANY (mana too low), drinking is what puts
        # him back in the fight — weight it ABOVE the staff-poke fallback (0.85) so
        # he tops up and blasts instead of conserving. Otherwise just keep topped.
        if self._dps_dry(state):
            slot = mp_slot if mp_slot is not None else rj_slot
            weight, tag = 0.9, "DPS-DRY (can't afford a cast)"
        elif mp_pct < 25:
            slot, weight, tag = mp_slot, 0.6, "LOW"
        elif mp_pct < 60:
            slot, weight, tag = mp_slot, 0.4, "TOPUP"
        else:
            return None

        if slot is None:
            return None  # no appropriate potion for this tier

        return AgentResponse(
            command=f"US {slot}",
            weight=weight,
            reasoning=f"Mana: {tag} MP={mp_pct}% drink slot {slot}",
        )
