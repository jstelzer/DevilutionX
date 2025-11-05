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
        3. Defer to Shopping agent when stores are visible
        4. Heal up if damaged
        """
        belt = state.get("belt", [])
        stats = state.get("stats")
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        player_pos = state.get("player", None)
        npcs = state.get("npcs", [])
        stores = state.get("stores", {})

        # Count healing potions in belt
        hp_potions = sum(1 for slot in belt if slot in ["hp", "rj"])
        mp_potions = sum(1 for slot in belt if slot == "mp")

        # Priority 1: Navigate to Pepin (healer) if health potions low
        # Trigger at 4 or fewer potions (companion says "running low" at 3)
        if hp_potions <= 4:
            # If stores are visible (we're near vendor), defer to Shopping agent
            if "hl" in stores and len(stores["hl"]) > 0:
                return AgentResponse(
                    command="NONE",
                    weight=0.0,
                    reasoning=f"Town: Healer shop open - deferring to Shopping agent"
                )

            # Find Pepin in NPC list
            pepin = next((npc for npc in npcs if npc["type"] == "hl"), None)

            if pepin:
                npc_x, npc_y = pepin["x"], pepin["y"]
                # Use Chebyshev distance (same as C++ store visibility check)
                dist = max(abs(npc_x - me_x), abs(npc_y - me_y))

                if dist <= 3:
                    # Close enough - interact to open shop
                    # High weight - this is critical (low potions!)
                    urgency_weight = 0.9 if hp_potions <= 1 else 0.8
                    return AgentResponse(
                        command=f"IN {pepin['id']}",
                        weight=urgency_weight,
                        reasoning=f"Town: Interacting with Pepin for potions ({hp_potions}/8)"
                    )
                elif dist > 3:
                    # Too far - navigate to Pepin
                    # High weight to beat movement agent (priority 5 × 0.8 = 4.0 beats movement's 3.0)
                    urgency_weight = 0.9 if hp_potions <= 1 else 0.8
                    return AgentResponse(
                        command=f"MV {npc_x} {npc_y}",
                        weight=urgency_weight,
                        reasoning=f"Town: Going to Pepin for potions ({hp_potions}/8, dist={dist})"
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
                    # Use Chebyshev distance (same as C++ store visibility check)
                    dist = max(abs(npc_x - me_x), abs(npc_y - me_y))

                    if dist <= 3:
                        # Close enough - interact to open shop
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

        # Priority 3: Heal up if damaged - visit Pepin
        # Even at 90% HP, worth topping off with Pepin (free healing!)
        if hp_pct < 100:
            # Find Pepin (the healer)
            npcs = state.get("npcs", [])
            pepin = next((npc for npc in npcs if npc["type"] == "hl"), None)

            if pepin:
                npc_x, npc_y = pepin["x"], pepin["y"]
                dist = max(abs(npc_x - me_x), abs(npc_y - me_y))

                if dist <= 3:
                    # Close enough - interact for healing
                    weight = 0.5 if hp_pct < 70 else 0.4
                    return AgentResponse(
                        command=f"IN {pepin['id']}",
                        weight=weight,
                        reasoning=f"Town: Talking to Pepin for healing (HP={hp_pct}%)"
                    )
                elif hp_pct < 70:
                    # Low HP and far away - prioritize getting to Pepin
                    return AgentResponse(
                        command=f"MV {npc_x} {npc_y}",
                        weight=0.5,
                        reasoning=f"Town: Going to Pepin for healing (HP={hp_pct}%, dist={dist})"
                    )
                elif dist <= 5:
                    # Close by and slightly hurt - might as well head over
                    return AgentResponse(
                        command=f"MV {npc_x} {npc_y}",
                        weight=0.15,  # Low priority if HP is okay
                        reasoning=f"Town: Moving to Pepin for quick top-off (HP={hp_pct}%)"
                    )
            elif hp_pct < 70:
                # Low HP but Pepin not visible - use a potion
                belt = state.get("belt", [])
                for i, item in enumerate(belt):
                    if item and item.get("type") == "hp":
                        return AgentResponse(
                            command=f"US {i}",
                            weight=0.3,
                            reasoning=f"Town: Using potion (HP={hp_pct}%, Pepin not found)"
                        )

        # Default: Low weight so movement takes over for player following
        return AgentResponse(
            command=f"MV {me_x} {me_y}",
            weight=0.1,
            reasoning="Town: Idle, all good"
        )
