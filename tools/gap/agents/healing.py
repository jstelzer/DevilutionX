"""
Healing Agent - Survival specialist
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class HealingAgent(BaseAgent):
    """Specialist for health management and potion usage"""

    def __init__(self, **kwargs):
        super().__init__(name="Healing", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Activate if HP < 90%"""
        me = state.get("me", [0, 0, 100, 100])
        hp_pct = me[2] if len(me) > 2 else 100
        return hp_pct < 90

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Decide if healing is needed based on HP and available potions.

        Priority healing thresholds:
        - HP < 20%: CRITICAL (weight 1.0) → prefer rejuv/full heal
        - HP 20-35%: URGENT (weight 0.8) → prefer heal potion
        - HP 35-50%: RECOMMENDED (weight 0.5)
        - HP 50-90%: OPTIONAL (weight 0.2)

        Coordination with LootAgent:
        - If no potions in belt, DON'T recommend USE (let LootAgent pick up)
        - Emergency retreat if HP critical and no potions
        """
        me = state.get("me", [0, 0, 100, 100])
        hp_pct = me[2] if len(me) > 2 else 100
        belt = state.get("belt", [])

        # Determine healing urgency
        if hp_pct < 20:
            weight = 1.0
            reasoning = "CRITICAL HP"
        elif hp_pct < 35:
            weight = 0.8
            reasoning = "URGENT HP"
        elif hp_pct < 50:
            weight = 0.5
            reasoning = "RECOMMENDED HP"
        elif hp_pct < 90:
            weight = 0.2
            reasoning = "OPTIONAL HP"
        else:
            return AgentResponse(command="NONE", weight=0.0, reasoning="Healing: HP OK")

        # Check if we have ANY healing potions
        healing_slots = [(slot, item_type) for slot, item_type in enumerate(belt) if item_type in ["hp", "rj"]]

        # No healing items available - coordinate with LootAgent
        if not healing_slots:
            # If HP critical and potions on ground, let LootAgent handle it
            loot = state.get("loot", [])
            if hp_pct < 30 and loot:
                return AgentResponse(
                    command="NONE",
                    weight=0.0,
                    reasoning=f"Healing: {reasoning} ({hp_pct}%) NO POTIONS - let LootAgent pickup"
                )

            # If HP critical with no potions and no loot, RETREAT to player
            if hp_pct < 30:
                player = state.get("player")
                if player:
                    plyr_x, plyr_y = player
                    return AgentResponse(
                        command=f"MV {plyr_x} {plyr_y}",
                        weight=0.9,
                        reasoning=f"Healing: RETREAT to player - {reasoning} ({hp_pct}%) NO POTIONS"
                    )

            return AgentResponse(
                command="NONE",
                weight=0.0,
                reasoning=f"Healing: {reasoning} ({hp_pct}%) but NO POTIONS"
            )

        # Find best potion in belt
        # Priority: rj (rejuv) > hp (healing) for critical, hp > rj for minor damage
        best_slot = None
        best_type = None

        for slot, item_type in healing_slots:
            # Critical HP: prefer rejuv
            if hp_pct < 20 and item_type == "rj":
                best_slot = slot
                best_type = "rejuv"
                break
            # Otherwise: prefer healing potion (more common)
            elif item_type == "hp" and best_type != "rj":
                best_slot = slot
                best_type = "heal"
            # Fallback to rejuv if no hp found
            elif item_type == "rj" and best_slot is None:
                best_slot = slot
                best_type = "rejuv"

        # Log belt state for debugging
        belt_status = ",".join(f"{i}:{t}" for i, t in enumerate(belt))
        logger.debug(f"Healing: Belt=[{belt_status}] choosing slot {best_slot} ({best_type})")

        return AgentResponse(
            command=f"US {best_slot}",
            weight=weight,
            reasoning=f"Healing: {reasoning} ({hp_pct}%) using {best_type} at slot {best_slot}"
        )
