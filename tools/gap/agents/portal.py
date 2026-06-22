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
        self._last_floor = None          # to detect when WE crossed a portal
        self._waiting_for_player = False  # "I went first — holding for you to cross"

    def should_activate(self, state: Dict[str, Any]) -> bool:
        theirs = [p for p in (state.get("portals") or []) if p.get("caster") == "them"]
        player_floor = state.get("player_floor")
        my_floor = state.get("floor")
        if my_floor is None or player_floor is None:
            return False

        # Waiting-state coordination: if WE just crossed a portal (our floor
        # changed) and the player isn't here yet, we went first — HOLD on this
        # side for them to follow instead of bouncing back through. Clear once
        # they join us.
        if self._last_floor is not None and my_floor != self._last_floor:
            self._waiting_for_player = (player_floor != my_floor)
        self._last_floor = my_floor
        if player_floor == my_floor:
            self._waiting_for_player = False
        if self._waiting_for_player:
            return False

        if not theirs:
            return False

        # Combat nuance: stay and help if the fight is survivable; only break off
        # to follow/retreat through the portal when we're low on HP AND have no
        # potions to recover (i.e. we'd likely die). Otherwise help, don't flee.
        if state.get("mobs"):
            hp_pct = state.get("me", [0, 0, 100, 100])[2]
            has_potions = any(s in ("hp", "rj") for s in state.get("belt", []))
            doomed = hp_pct <= 30 and not has_potions
            if not doomed:
                return False

        # Case A — already separated: the player is on a different floor and
        # their portal here leads to them. Step through to catch up.
        if player_floor != my_floor:
            return True

        # Case B — together and the player is about to cross their OWN portal.
        # It closes the instant they step through, so she must go FIRST. Trigger
        # when the player is close to their portal (i.e. about to use it).
        player_pos = state.get("player")
        if player_pos:
            px, py = player_pos
            for p in theirs:
                if max(abs(p["x"] - px), abs(p["y"] - py)) <= 6:
                    return True
        return False

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
