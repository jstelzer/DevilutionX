"""
Stats Agent - Character progression specialist
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


# Class names for logging
CLASS_NAMES = {
    0: "Warrior",
    1: "Rogue",
    2: "Sorcerer",
    3: "Monk",
    4: "Bard",
    5: "Barbarian",
}


class StatsAgent(BaseAgent):
    """Specialist for stat allocation and level-up decisions"""

    def __init__(self, **kwargs):
        super().__init__(name="Stats", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Only activate if stat points available and safe context"""
        stats = state.get("stats")
        if not stats or stats.get("pts", 0) == 0:
            return False

        # Don't allocate stats during combat
        if len(state.get("mobs", [])) > 0:
            return False

        # Don't allocate in town (let town agent handle town stuff)
        if state.get("in_town", False):
            return False

        return True

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Decide where to allocate stat points based on class.

        Allocation priorities by class:
        - Warrior/Barbarian: STR > VIT > DEX
        - Rogue/Monk/Bard: DEX > VIT > STR
        - Sorcerer: MAG > VIT > DEX

        Always maintains minimum VIT for survival.
        """
        stats = state.get("stats")
        if not stats:
            return AgentResponse(command="NONE", weight=0.0, reasoning="Stats: No stat data")

        pts_available = stats.get("pts", 0)
        if pts_available == 0:
            return AgentResponse(command="NONE", weight=0.0, reasoning="Stats: No points to allocate")

        char_class = stats.get("class", 0)
        class_name = CLASS_NAMES.get(char_class, "Unknown")

        # Current stats
        str_val = stats.get("str", 0)
        dex_val = stats.get("dex", 0)
        mag_val = stats.get("mag", 0)
        vit_val = stats.get("vit", 0)
        lvl = stats.get("lvl", 1)

        # Determine allocation based on class
        stat_choice = None
        reasoning = ""

        # Warrior/Barbarian: STR > VIT > DEX
        if char_class in [0, 5]:
            # VIT threshold: aim for at least 2x level for survivability
            if vit_val < lvl * 2:
                stat_choice = "VIT"
                reasoning = f"{class_name}: VIT too low ({vit_val} < {lvl*2})"
            # Otherwise pump STR
            else:
                stat_choice = "STR"
                reasoning = f"{class_name}: Maximize STR (current {str_val})"

        # Rogue/Monk/Bard: DEX > VIT > STR
        elif char_class in [1, 3, 4]:
            # VIT threshold: aim for at least 1.5x level
            if vit_val < int(lvl * 1.5):
                stat_choice = "VIT"
                reasoning = f"{class_name}: VIT too low ({vit_val} < {int(lvl*1.5)})"
            # Otherwise pump DEX
            else:
                stat_choice = "DEX"
                reasoning = f"{class_name}: Maximize DEX (current {dex_val})"

        # Sorcerer: MAG > VIT > DEX
        elif char_class == 2:
            # VIT threshold: aim for at least 1.2x level (sorcerers are squishy)
            if vit_val < int(lvl * 1.2):
                stat_choice = "VIT"
                reasoning = f"{class_name}: VIT too low ({vit_val} < {int(lvl*1.2)})"
            # Otherwise pump MAG
            else:
                stat_choice = "MAG"
                reasoning = f"{class_name}: Maximize MAG (current {mag_val})"

        if not stat_choice:
            return AgentResponse(command="NONE", weight=0.0, reasoning="Stats: No allocation decision")

        # High weight when we have points to allocate
        weight = 0.8

        return AgentResponse(
            command=f"ADDSTAT {stat_choice}",
            weight=weight,
            reasoning=f"Stats: {reasoning} ({pts_available} pts available)"
        )
