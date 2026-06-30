"""
Movement Agent - Positioning and navigation specialist
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class MovementAgent(BaseAgent):
    """Specialist for positioning and player-following"""

    # Follow hysteresis: a single distance threshold makes the follow weight flip
    # every time the player drifts one tile across it, and that flip changes the
    # council winner — she ping-pongs between two tiles forever (measured as the
    # corpus-wide Town<->Movement x406 oscillation, 2026-06-30). A held stance with
    # a START radius (begin following) wider than the STOP radius (settle) breaks
    # the limit cycle: once she's inside, the player must drift meaningfully — not
    # one jittery tile — before she chases again. (This is the "skeleton is the
    # cache bust" principle in miniature: re-plan on meaningful change, a mini
    # preview of B5 intent leases — the follow stance is a held lease.)
    FOLLOW_START = 5  # begin following once the player is this far (Manhattan)
    FOLLOW_STOP = 2   # ...and keep going until back within this

    def __init__(self, **kwargs):
        super().__init__(name="Movement", **kwargs)
        self._following = False

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Movement always active (fallback agent)"""
        return True

    def _update_following(self, dist: int) -> bool:
        """Hysteretic follow stance: True only outside START, back to False inside
        STOP, and *held* in the band between (history decides) — so a one-tile
        jitter at the boundary can't flip it."""
        if self._following:
            if dist <= self.FOLLOW_STOP:
                self._following = False
        elif dist > self.FOLLOW_START:
            self._following = True
        return self._following

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

        # In town: follow with hysteresis so she settles next to the player
        # instead of jittering across a single follow threshold.
        if in_town:
            if self._update_following(dist_to_player):
                return AgentResponse(
                    command=f"MV {plyr_x} {plyr_y}",
                    weight=0.7,
                    reasoning=f"Movement: Following player in town (dist={dist_to_player})"
                )
            else:
                return AgentResponse(
                    command=f"MV {me_x} {me_y}",
                    weight=0.2,
                    reasoning=f"Movement: Holding near player in town (dist={dist_to_player})"
                )

        # In dungeon: keep close so she stays in the fight instead of trailing.
        # Same hysteresis band (START=5 / STOP=2) so closing the gap doesn't flip.
        if self._update_following(dist_to_player):
            return AgentResponse(
                command=f"MV {plyr_x} {plyr_y}",
                weight=0.85,
                reasoning=f"Movement: Following player (dist={dist_to_player})"
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
