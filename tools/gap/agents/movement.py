"""
Movement Agent - Positioning and navigation specialist
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class MovementAgent(BaseAgent):
    """Specialist for positioning and player-following"""

    def __init__(self, **kwargs):
        super().__init__(name="Movement", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Movement always active (fallback agent)"""
        return True

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Recommend movement based on:
        - Player position (follow/stay near)
        - Monster positions (tactical positioning/retreat)
        - Danger level

        Uses RULE-BASED logic instead of LLM to avoid model switching delays.
        """
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        player_pos = state.get("player", None)
        in_town = state.get("in_town", False)

        if not player_pos:
            # No player position - stand still
            return AgentResponse(
                command=f"MV {me_x} {me_y}",
                weight=0.1,
                reasoning="Movement: No player position"
            )

        plyr_x, plyr_y = player_pos
        dist_to_player = abs(plyr_x - me_x) + abs(plyr_y - me_y)
        mobs = state.get("mobs", [])

        # Rule-based movement (no LLM - faster and no model switching)

        # In town: always follow player closely
        if in_town:
            if dist_to_player > 3:
                return AgentResponse(
                    command=f"MV {plyr_x} {plyr_y}",
                    weight=0.7,
                    reasoning=f"Movement: Following player in town (dist={dist_to_player})"
                )
            else:
                return AgentResponse(
                    command=f"MV {me_x} {me_y}",
                    weight=0.2,
                    reasoning="Movement: Near player in town"
                )

        # In dungeon: maintain 3-7 tile distance
        if dist_to_player > 8:
            # Too far - follow closely
            return AgentResponse(
                command=f"MV {plyr_x} {plyr_y}",
                weight=0.8,
                reasoning=f"Movement: Too far from player (dist={dist_to_player})"
            )
        elif dist_to_player < 2:
            # Too close - give some space
            # Move slightly away from player
            away_x = me_x + (me_x - plyr_x)
            away_y = me_y + (me_y - plyr_y)
            return AgentResponse(
                command=f"MV {away_x} {away_y}",
                weight=0.5,
                reasoning=f"Movement: Too close to player (dist={dist_to_player})"
            )
        else:
            # Good distance (2-8 tiles) - stay put unless combat
            if len(mobs) > 2 and hp_pct < 40:
                # Retreat toward player if low HP and monsters
                return AgentResponse(
                    command=f"MV {plyr_x} {plyr_y}",
                    weight=0.6,
                    reasoning="Movement: Retreating to player (low HP + combat)"
                )
            else:
                # Good position
                return AgentResponse(
                    command=f"MV {me_x} {me_y}",
                    weight=0.3,
                    reasoning=f"Movement: Good position (dist={dist_to_player})"
                )
