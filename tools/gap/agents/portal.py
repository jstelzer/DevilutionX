"""
Portal Agent - follow the human through a town portal.

A town portal closes when its *caster* steps through it. So:
- someone else's portal ("them"): she must go FIRST — rush through before the
  caster closes it behind them.
- her own portal ("me"): she does NOT rush; the human goes first. We simply
  don't act on it here. (The coordination layer adds the explicit "you go first,
  I'll follow / all clear" waiting + callouts.)

Like stairs, stepping onto the portal tile triggers the engine's warp because
she's MyPlayer in her own client.
"""

import logging
from typing import Dict, Any, Optional

from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class PortalAgent(BaseAgent):
    """Walks the AI through the human's town portal to follow across levels."""

    def __init__(self, **kwargs):
        super().__init__(name="Portal", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        portals = state.get("portals") or []
        player_floor = state.get("player_floor")
        my_floor = state.get("floor")
        # Only a portal cast by someone else, and only when the player is on a
        # different floor (so stepping through catches us up to them).
        theirs = [p for p in portals if p.get("caster") == "them"]
        return (
            len(theirs) > 0
            and player_floor is not None
            and my_floor is not None
            and player_floor != my_floor
        )

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        portals = state.get("portals") or []
        me_x, me_y, _, _ = state.get("me", [0, 0, 100, 100])

        theirs = [p for p in portals if p.get("caster") == "them"]
        if not theirs:
            return None

        target = min(theirs, key=lambda p: max(abs(p["x"] - me_x), abs(p["y"] - me_y)))
        px, py = target["x"], target["y"]
        dist = max(abs(px - me_x), abs(py - me_y))

        logger.info(
            f"Portal: stepping into the player's portal at ({px},{py}) dist={dist} "
            f"to follow to floor {state.get('player_floor')} (go first — it closes when they cross)"
        )
        return AgentResponse(
            command=f"MV {px} {py}",
            weight=0.95,  # rush: the portal closes the instant the caster steps through
            reasoning=f"Portal: through player's portal to floor {state.get('player_floor')}",
        )
