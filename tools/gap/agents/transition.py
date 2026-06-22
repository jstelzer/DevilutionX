"""
Transition Agent - follow the human player across dungeon levels via stairs.

In the true-multiplayer model the AI is its own client's MyPlayer, so simply
standing on a stair/level-transition tile triggers the engine's normal level
change (CheckTriggers -> StartNewLvl) — exactly like a human stepping on stairs.
So "follow into the dungeon" is just: when the player is on a different floor
and we can see the matching stairs, walk onto them.
"""

import logging
from typing import Dict, Any, Optional

from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class TransitionAgent(BaseAgent):
    """Walks the AI onto the stairs to follow the player to another floor."""

    def __init__(self, **kwargs):
        super().__init__(name="Transition", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        my_floor = state.get("floor")
        player_floor = state.get("player_floor")
        stairs = state.get("stairs") or []
        # Only when we know the player's floor, it differs from ours, and there
        # are level-transition triggers to act on. (Walking to the player's
        # cross-floor coordinates is meaningless — we must change levels ourselves.)
        return (
            player_floor is not None
            and my_floor is not None
            and player_floor != my_floor
            and len(stairs) > 0
        )

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        my_floor = state["floor"]
        player_floor = state["player_floor"]
        stairs = state.get("stairs") or []
        me_x, me_y, _, _ = state.get("me", [0, 0, 100, 100])

        # Go the direction the player went, and pick the nearest matching trigger.
        want = "down" if player_floor > my_floor else "up"
        candidates = [s for s in stairs if s.get("type") == want]
        if not candidates:
            # No trigger in the needed direction is in view yet; let other agents
            # act (the right stairs may come into view as she moves).
            return None

        target = min(candidates, key=lambda s: max(abs(s["x"] - me_x), abs(s["y"] - me_y)))
        sx, sy = target["x"], target["y"]
        dist = max(abs(sx - me_x), abs(sy - me_y))

        # Walk onto the exact trigger tile. Standing on it makes the engine fire
        # the level change automatically (we're MyPlayer in our own client).
        logger.info(
            f"Transition: player on floor {player_floor}, we're on {my_floor}; "
            f"heading to {want}-trigger at ({sx},{sy}) dist={dist}"
        )
        return AgentResponse(
            command=f"MV {sx} {sy}",
            weight=0.9,  # catching up to the player beats idle/town wandering
            reasoning=f"Transition: to {want}-trigger, follow player to floor {player_floor}",
        )
