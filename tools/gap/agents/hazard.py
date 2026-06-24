"""
Hazard Agent - "see the fire" survival reflex.

The DSL now publishes an ``HZ=`` danger layer (Fire Wall, Inferno, incoming
fireballs/lightning, acid pools — any hostile missile/AoE near her). Before this,
standing in fire was an *invisible* threat: she'd cheerfully attack from inside an
Inferno because nothing in her state said the tile hurt. This agent is the
reflex that fixes that — when she's in (or adjacent to) a hazard, it steps her to
the nearest safe tile at survival priority.

Rule-based (no LLM): like MovementAgent, this must fire instantly. Element-aware
via the hazard ``kind`` so Track D's *fire tolerance* slider can later scale how
long a given character is willing to linger (the ``_fire_tolerance`` hook). The
default tolerance is low — she avoids fire unless a personality says otherwise.
"""

import logging
from typing import Any, Dict, Optional

from hazards import hazards_within, is_tile_dangerous, nearest_safe_tile

from .base import AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


class HazardAgent(BaseAgent):
    """Step out of active hazards (fire/lightning/AoE)."""

    def __init__(self, **kwargs):
        super().__init__(name="Hazard", **kwargs)
        self.use_memory_context = False  # reflex — no prompt, no preamble

    def should_activate(self, state: Dict[str, Any]) -> bool:
        # No hazards underground? nothing to do. (Town has no combat hazards.)
        if state.get("in_town", False):
            return False
        if not state.get("hazards"):
            return False
        me_x, me_y, _, _ = state.get("me", [0, 0, 100, 100])
        # Trigger if a hazard is on our tile or one step away (preemptive dodge).
        return is_tile_dangerous(state, me_x, me_y, radius=1)

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        me_x, me_y, _, _ = state.get("me", [0, 0, 100, 100])

        # Standing directly ON a hazard tile is urgent; merely adjacent is a dodge.
        on_tile = is_tile_dangerous(state, me_x, me_y, radius=0)

        # Step out toward the party, not off alone into the dark.
        safe = nearest_safe_tile(state, prefer=state.get("player"), search=5, radius=1)
        if safe is None:
            # Boxed in — every nearby tile is dangerous. Let healing/extraction or
            # combat handle it; flailing toward another fire tile helps nobody.
            logger.warning("Hazard: surrounded by hazards, no safe tile in range")
            return None

        # Fire tolerance damps urgency (never to zero — a hard survival floor stays,
        # so even a reckless character won't face-tank an Inferno indefinitely).
        tol = self._fire_tolerance(state)
        base = 0.97 if on_tile else 0.6
        weight = base * (1.0 - 0.6 * tol)

        kinds = "/".join(sorted({hz["kind"] for hz in hazards_within(state, me_x, me_y, 1)}))
        reasoning = f"Hazard: stepping out of {kinds} to {safe[0]},{safe[1]} ({'ON' if on_tile else 'adj'})"
        if on_tile:
            logger.warning(f"🔥 {reasoning}")
        return AgentResponse(command=f"MV {safe[0]} {safe[1]}", weight=weight, reasoning=reasoning)

    def _fire_tolerance(self, state: Dict[str, Any]) -> float:
        """Track D hook: a personality slider in [0,1] (higher = lingers in fire).

        Until the D1 sliders land, default low so she avoids fire. Reads a cached
        slider if the personality layer ever exposes one — never touches the DB on
        the hot path.
        """
        p = self.personality
        if p is not None:
            try:
                getter = getattr(p, "get_slider", None)
                if callable(getter):
                    v = getter("fire_tolerance")
                    if v is not None:
                        return max(0.0, min(1.0, float(v)))
            except Exception:  # a tuning hook must never break the reflex
                pass
        return 0.1
