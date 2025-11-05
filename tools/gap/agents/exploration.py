"""
Exploration Agent - Handles object interactions (doors, chests, barrels)
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class ExplorationAgent(BaseAgent):
    """Specialist for dungeon exploration - opening doors, chests, barrels"""

    def __init__(self, **kwargs):
        super().__init__(name="Exploration", **kwargs)
        self.last_interact_tick = 0
        self.interact_cooldown = 30  # Ticks between interactions (1 second)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Activate when there are nearby objects to interact with.
        Only active in dungeon (not town).
        """
        if state.get("in_town", False):
            return False

        objects = state.get("objects", [])
        return len(objects) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Evaluate which objects to interact with.

        Priority:
        1. Chests (high value loot)
        2. Doors (exploration/path opening)
        3. Barrels (minor loot)

        Safety:
        - Avoid trapped chests when low HP
        - Avoid explosive barrels in combat
        - Check if already on cooldown
        """
        me_x, me_y, hp_pct, mp_pct = state["me"]
        objects = state.get("objects", [])
        mobs = state.get("mobs", [])
        tick = state.get("tick", 0)

        # Check cooldown
        if tick - self.last_interact_tick < self.interact_cooldown:
            return None

        # Check if in combat (don't interact with objects during combat)
        if len(mobs) > 2:  # Multiple monsters nearby
            logger.debug(f"Exploration: In combat ({len(mobs)} monsters), skipping objects")
            return None

        # Find closest interactable object by priority
        best_object = None
        best_score = 0.0

        for obj in objects:
            obj_type = obj["type"]
            obj_id = obj["id"]
            obj_x, obj_y = obj["x"], obj["y"]
            dist = obj["dist"]

            # Skip if too far (need to be adjacent)
            if dist > 2:
                continue

            # Score objects by priority and safety
            score = 0.0
            reasoning = ""

            if obj_type == "ch":  # Chest (normal)
                score = 0.9
                reasoning = f"Exploration: Open chest (dist={dist})"
            elif obj_type == "tc":  # Trapped chest
                if hp_pct > 50:
                    score = 0.8  # Safe to open if healthy
                    reasoning = f"Exploration: Open trapped chest (HP={hp_pct}%, dist={dist})"
                else:
                    score = 0.3  # Risky when low HP
                    reasoning = f"Exploration: Risky trapped chest (HP={hp_pct}%, dist={dist})"
            elif obj_type == "dr":  # Door
                score = 0.7
                reasoning = f"Exploration: Open door (dist={dist})"
            elif obj_type == "ba":  # Barrel
                score = 0.5
                reasoning = f"Exploration: Break barrel (dist={dist})"
            elif obj_type == "xb":  # Explosive barrel
                if len(mobs) == 0:
                    score = 0.4  # Safe when no monsters
                    reasoning = f"Exploration: Break explosive barrel (no combat, dist={dist})"
                else:
                    score = 0.0  # Don't break during combat!
                    reasoning = f"Exploration: Skipping explosive barrel (combat active)"
            elif obj_type == "sh":  # Shrine
                # Shrines are blocked for companions (see objects.cpp restrictions)
                score = 0.0
                logger.debug(f"Exploration: Shrine at ({obj_x},{obj_y}) - companions cannot use shrines")

            if score > best_score:
                best_score = score
                best_object = (obj_id, obj_x, obj_y, reasoning)

        if best_object and best_score > 0.0:
            obj_id, obj_x, obj_y, reasoning = best_object

            # Check if we're adjacent (within 1 tile)
            dx = abs(obj_x - me_x)
            dy = abs(obj_y - me_y)

            if dx <= 1 and dy <= 1:
                # Adjacent - interact directly
                self.last_interact_tick = tick
                logger.info(f"Exploration: Interacting with object {obj_id} at ({obj_x},{obj_y})")
                return AgentResponse(
                    command=f"IN {obj_id}",
                    weight=best_score,
                    reasoning=reasoning
                )
            else:
                # Not adjacent - move closer
                logger.info(f"Exploration: Moving to object {obj_id} at ({obj_x},{obj_y})")
                return AgentResponse(
                    command=f"MV {obj_x} {obj_y}",
                    weight=best_score * 0.8,  # Lower weight for movement
                    reasoning=f"Exploration: Moving to {reasoning.split(':')[1].strip()}"
                )

        return None
