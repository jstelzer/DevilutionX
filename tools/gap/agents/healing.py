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

        Priority healing thresholds (adjusts for bootstrap mode):
        - HP < 20%: CRITICAL (weight 1.0) → prefer rejuv/full heal
        - HP 20-35%: URGENT (weight 0.8) → prefer heal potion
        - HP 35-50%: RECOMMENDED (weight 0.5)
        - HP 50-90%: OPTIONAL (weight 0.2)

        Bootstrap mode (low level + low resources):
        - Raises thresholds by +15% (use potions earlier)

        Coordination with LootAgent:
        - If no potions in belt, DON'T recommend USE (let LootAgent pick up)
        - Emergency retreat if HP critical and no potions
        """
        me = state.get("me", [0, 0, 100, 100])
        hp_pct = me[2] if len(me) > 2 else 100
        belt = state.get("belt", [])

        # Check for bootstrap mode adjustments
        bootstrap_boost = 0
        if self.profile and self.profile.bootstrap_mode:
            bootstrap_boost = 15  # Use potions 15% earlier in bootstrap mode

        # Determine healing urgency (with bootstrap adjustments)
        if hp_pct < (20 + bootstrap_boost):
            weight = 1.0
            reasoning = "CRITICAL HP" + (" [BOOTSTRAP]" if bootstrap_boost else "")
        elif hp_pct < (35 + bootstrap_boost):
            weight = 0.8
            reasoning = "URGENT HP" + (" [BOOTSTRAP]" if bootstrap_boost else "")
        elif hp_pct < (50 + bootstrap_boost):
            weight = 0.5
            reasoning = "RECOMMENDED HP" + (" [BOOTSTRAP]" if bootstrap_boost else "")
        elif hp_pct < 90:
            weight = 0.2
            reasoning = "OPTIONAL HP"
        else:
            return AgentResponse(command="NONE", weight=0.0, reasoning="Healing: HP OK")

        # Check if we have ANY healing items (potions or scrolls)
        healing_slots = [(slot, item_type) for slot, item_type in enumerate(belt)
                        if item_type in ["hp", "rj", "sh"]]  # sh = healing scroll

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

        # Find best healing item in belt
        # Priority: rj (rejuv) > hp (healing) > sh (scroll) for critical
        #           hp > rj > sh for minor damage (save scrolls when possible)
        best_slot = None
        best_type = None
        best_command = None

        for slot, item_type in healing_slots:
            # Critical HP: prefer rejuv > healing > scroll
            if hp_pct < 20:
                if item_type == "rj":
                    best_slot = slot
                    best_type = "rejuv"
                    best_command = "US"
                    break
                elif item_type == "hp" and best_type != "rj":
                    best_slot = slot
                    best_type = "heal"
                    best_command = "US"
                elif item_type == "sh" and best_slot is None:
                    best_slot = slot
                    best_type = "heal_scroll"
                    best_command = "CS"
            # Normal HP: prefer potions over scrolls (save scrolls for when we're out of potions)
            else:
                if item_type == "hp" and best_type not in ["rj", "heal"]:
                    best_slot = slot
                    best_type = "heal"
                    best_command = "US"
                elif item_type == "rj" and best_type not in ["hp", "heal"]:
                    best_slot = slot
                    best_type = "rejuv"
                    best_command = "US"
                elif item_type == "sh" and best_slot is None:
                    best_slot = slot
                    best_type = "heal_scroll"
                    best_command = "CS"

        # Log belt state for debugging
        belt_status = ",".join(f"{i}:{t}" for i, t in enumerate(belt))
        logger.debug(f"Healing: Belt=[{belt_status}] choosing slot {best_slot} ({best_type})")

        return AgentResponse(
            command=f"{best_command} {best_slot}",
            weight=weight,
            reasoning=f"Healing: {reasoning} ({hp_pct}%) using {best_type} at slot {best_slot}"
        )
