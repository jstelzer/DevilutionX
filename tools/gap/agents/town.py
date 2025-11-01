"""
Town Agent - NPC interaction and shopping specialist
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class TownAgent(BaseAgent):
    """Specialist for town activities: shopping, repair, identify"""

    def __init__(self, **kwargs):
        super().__init__(name="Town", **kwargs)
        self.last_action = None

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Only activate when in town"""
        return state.get("in_town", False)

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Decide town actions:
        1. Navigate to Pepin if health potions needed
        2. Navigate to Adria if mana potions needed (for casters)
        3. Interact with shop when adjacent
        4. Heal up if damaged
        """
        belt = state.get("belt", [])
        stats = state.get("stats")
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        player_pos = state.get("player", None)
        npcs = state.get("npcs", [])

        # Count healing potions in belt
        hp_potions = sum(1 for slot in belt if slot in ["hp", "rj"])
        mp_potions = sum(1 for slot in belt if slot == "mp")

        # Priority 1: Navigate to Pepin (healer) if health potions low
        if hp_potions < 3:
            # Find Pepin in NPC list
            pepin = next((npc for npc in npcs if npc["type"] == "hl"), None)

            if pepin:
                npc_x, npc_y = pepin["x"], pepin["y"]
                dist = abs(npc_x - me_x) + abs(npc_y - me_y)

                if dist <= 1:
                    # Adjacent to Pepin - interact to open shop
                    return AgentResponse(
                        command=f"IN {pepin['id']}",
                        weight=0.8,
                        reasoning=f"Town: Interacting with Pepin to buy potions ({hp_potions}/8)"
                    )
                elif dist > 3:
                    # Too far - navigate to Pepin
                    return AgentResponse(
                        command=f"MV {npc_x} {npc_y}",
                        weight=0.7,
                        reasoning=f"Town: Going to Pepin for potions ({hp_potions}/8, dist={dist})"
                    )
                else:
                    # Getting close - move adjacent
                    return AgentResponse(
                        command=f"MV {npc_x} {npc_y}",
                        weight=0.6,
                        reasoning=f"Town: Approaching Pepin ({hp_potions}/8, dist={dist})"
                    )
            else:
                # Pepin not found - mention need
                return AgentResponse(
                    command="SAY Need to find Pepin for potions",
                    weight=0.3,
                    reasoning=f"Town: Low HP potions ({hp_potions}/8) but Pepin not visible"
                )

        # Priority 2: Navigate to Adria (witch) for mana potions (casters)
        if stats and stats.get("class") == 2:  # Sorcerer
            if mp_potions < 2:
                # Find Adria in NPC list
                adria = next((npc for npc in npcs if npc["type"] == "wt"), None)

                if adria:
                    npc_x, npc_y = adria["x"], adria["y"]
                    dist = abs(npc_x - me_x) + abs(npc_y - me_y)

                    if dist <= 1:
                        # Adjacent to Adria - interact to open shop
                        return AgentResponse(
                            command=f"IN {adria['id']}",
                            weight=0.75,
                            reasoning=f"Town: Interacting with Adria for mana potions ({mp_potions}/8)"
                        )
                    elif dist > 3:
                        # Too far - navigate to Adria
                        return AgentResponse(
                            command=f"MV {npc_x} {npc_y}",
                            weight=0.6,
                            reasoning=f"Town: Going to Adria for mana ({mp_potions}/8, dist={dist})"
                        )

        # Priority 3: Heal up if damaged - move to fountain
        # Fountain is usually near town center, for now just stay put
        if hp_pct < 100:
            return AgentResponse(
                command="SAY Healing at fountain",
                weight=0.2,
                reasoning=f"Town: Need healing ({hp_pct}%)"
            )

        # Default: Low weight so movement takes over for player following
        return AgentResponse(
            command=f"MV {me_x} {me_y}",
            weight=0.1,
            reasoning="Town: Idle, all good"
        )
