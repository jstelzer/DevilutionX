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

    def should_activate(self, state: Dict[str, Any]) -> bool:
        # Only casters bother with mana potions.
        stats = state.get("stats") or {}
        if stats.get("mag", 0) < CASTER_MAGIC_MIN:
            return False
        # No casting in town (and the shops/refill agents own town behavior).
        if state.get("in_town"):
            return False
        me = state.get("me", [0, 0, 100, 100])
        mp_pct = me[3] if len(me) > 3 else 100
        if mp_pct >= 40:
            return False
        # Only worth a potion when there's actually something to cast at —
        # mana doesn't regen passively, so don't burn potions while wandering.
        if not state.get("mobs"):
            return False
        # Need a mana potion (or a rejuv, which also restores mana) in the belt.
        belt = state.get("belt", [])
        return any(t in ("mp", "rj") for t in belt)

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        me = state.get("me", [0, 0, 100, 100])
        mp_pct = me[3] if len(me) > 3 else 100
        belt = state.get("belt", [])

        mp_slot = next((i for i, t in enumerate(belt) if t == "mp"), None)
        rj_slot = next((i for i, t in enumerate(belt) if t == "rj"), None)

        # Prefer a plain mana potion. Only reach for a rejuv when mana is
        # critical and there's no mana potion — rejuv also heals, so we don't
        # want to burn one just to top off the blue bar.
        if mp_pct < 15:
            slot = mp_slot if mp_slot is not None else rj_slot
            weight = 0.7
            tag = "CRITICAL"
        elif mp_pct < 25:
            slot = mp_slot
            weight = 0.5
            tag = "LOW"
        else:  # < 40
            slot = mp_slot
            weight = 0.3
            tag = "TOPUP"

        if slot is None:
            return None  # no appropriate potion for this urgency tier

        return AgentResponse(
            command=f"US {slot}",
            weight=weight,
            reasoning=f"Mana: {tag} MP={mp_pct}% drink slot {slot}",
        )
