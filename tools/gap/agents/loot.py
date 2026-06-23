"""
Loot Agent - Item evaluation and pickup specialist
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class LootAgent(BaseAgent):
    """Specialist for item evaluation and pickup decisions"""

    def __init__(self, **kwargs):
        super().__init__(name="Loot", **kwargs)
        self.failed_pickups = {}  # item_id -> attempt_count
        self.last_loot_state = []  # Track items from last tick
        self.last_pk_attempt = None  # item_id we actually issued PK for last tick
        self.recently_dropped = {}  # item_position -> tick_when_dropped (avoid picking up what we just dropped)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """Only activate if items nearby and not in combat"""
        # Don't loot during active combat (3+ monsters nearby)
        if len(state.get("mobs", [])) > 3:
            return False

        return len(state.get("loot", [])) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Evaluate loot and recommend best item to pick up.

        Priority scoring:
        - Gold: always high value
        - Unique items: highest priority
        - Magic items: medium-high priority
        - Useful item types: weapons/armor > misc
        - Distance: closer = higher priority
        - Belt space: consider for potions
        """
        loot = state.get("loot", [])
        if not loot:
            return AgentResponse(command="NONE", weight=0.0, reasoning="Loot: No items")

        # Detect picked up items (items that disappeared from state)
        current_item_ids = {item.get('id') for item in loot}

        # Clear tracking for items that are gone (picked up by anyone, or despawned)
        for item_id in list(self.failed_pickups):
            if item_id not in current_item_ids:
                self.failed_pickups.pop(item_id, None)

        # A pickup only counts as FAILED if we issued PK for that item last tick
        # AND it is still on the ground AND still adjacent now. Merely walking
        # toward an item, or the council choosing another action and moving us
        # away, must NOT count against it — that was the premature-blacklist bug.
        if self.last_pk_attempt is not None:
            attempted = next((it for it in loot if it.get('id') == self.last_pk_attempt), None)
            if attempted is not None and attempted.get('dist', 999) <= 1:
                self.failed_pickups[self.last_pk_attempt] = self.failed_pickups.get(self.last_pk_attempt, 0) + 1
                if self.failed_pickups[self.last_pk_attempt] >= 3:
                    logger.warning(f"Loot: Item {self.last_pk_attempt} failed PK 3+ times, blacklisting")
        self.last_pk_attempt = None  # reset; set again below only if we PK this tick

        # Update state tracking
        self.last_loot_state = loot

        belt = state.get("belt", [])
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])

        # Count empty belt slots
        empty_belt_slots = sum(1 for slot in belt if slot == "em")

        # Evaluate each item
        best_item = None
        best_score = 0.0

        current_tick = state.get("tick", 0)

        # Clean up old dropped items (older than 10 seconds = 200 ticks)
        self.recently_dropped = {
            pos: tick for pos, tick in self.recently_dropped.items()
            if current_tick - tick < 200
        }

        for item in loot:
            item_id = item.get('id', -1)
            item_pos = (item.get('x', 0), item.get('y', 0))

            # Skip blacklisted items (failed 3+ times)
            if self.failed_pickups.get(item_id, 0) >= 3:
                continue

            # Skip items we just dropped (within last 10 seconds)
            if item_pos in self.recently_dropped:
                ticks_since_drop = current_tick - self.recently_dropped[item_pos]
                logger.debug(f"Loot: Skipping recently dropped item at {item_pos} (dropped {ticks_since_drop} ticks ago)")
                continue

            score = self._score_item(item, empty_belt_slots, hp_pct)

            if score > best_score:
                best_score = score
                best_item = item

        # No worthwhile items
        if best_score < 0.3 or best_item is None:
            return AgentResponse(
                command="NONE",
                weight=0.0,
                reasoning="Loot: No valuable items"
            )

        # Check if we need to move to item first
        item_dist = best_item.get('dist', 999)
        item_x = best_item.get('x', 0)
        item_y = best_item.get('y', 0)
        item_id = best_item.get('id', 0)
        item_desc = f"{best_item.get('quality', 'n')}/{best_item.get('type', 'ms')}"

        # If item is far away, move toward it first (this is NOT a pickup attempt,
        # so it must not be recorded as one — see failure tracking above).
        if item_dist > 1:
            return AgentResponse(
                command=f"MV {item_x} {item_y}",
                weight=min(best_score, 1.0),
                reasoning=f"Loot: Moving to {item_desc} value={best_item.get('value', 0)} dist={item_dist}"
            )

        # Item is adjacent - pick it up. Record the real attempt so we can tell
        # next tick whether the PK actually worked.
        self.last_pk_attempt = item_id
        return AgentResponse(
            command=f"PK {item_id}",
            weight=min(best_score, 1.0),
            reasoning=f"Loot: Pickup {item_desc} value={best_item.get('value', 0)} dist={item_dist}"
        )

    def _score_item(self, item: Dict[str, Any], empty_belt_slots: int, hp_pct: int) -> float:
        """
        Score an item for pickup priority.

        Returns:
            0.0-1.5+ score (can exceed 1.0 for exceptional items)
        """
        score = 0.0
        item_type = item.get("type", "ms")
        quality = item.get("quality", "n")
        value = item.get("value", 0)
        dist = item.get("dist", 999)
        high_priority = False  # set for magic/unique class gear — those ignore distance

        # Quality multiplier
        quality_mult = {
            "u": 3.0,  # unique
            "m": 2.0,  # magic
            "n": 1.0,  # normal
        }.get(quality, 1.0)

        # Type scoring (base value before profile adjustments)
        type_score = {
            "go": 1.0,  # gold - always good
            "sw": 0.8,  # weapons
            "ax": 0.8,
            "bw": 0.8,
            "mc": 0.8,
            "st": 0.8,
            "sh": 0.7,  # armor
            "la": 0.7,
            "ma": 0.7,
            "ha": 0.7,
            "hl": 0.7,
            "rg": 0.9,  # jewelry - usually valuable
            "am": 0.9,
            "ms": 0.3,  # misc - low priority unless magic/unique
        }.get(item_type, 0.3)

        # Profile-based adjustments (prioritize preferred weapon/armor types)
        if self.profile:
            # Boost score for preferred weapon types
            if item_type in self.profile.preferred_weapons:
                type_score *= 1.3  # 30% boost for class-appropriate weapons
                logger.debug(f"Loot: {self.profile.class_name} prefers {item_type} - boosting score")
            # Boost score for preferred armor types
            elif item_type in self.profile.preferred_armor:
                type_score *= 1.2  # 20% boost for class-appropriate armor
                logger.debug(f"Loot: {self.profile.class_name} prefers {item_type} - boosting score")

            # CRITICAL: Always pick up unidentified magic/unique items of preferred types
            # These could be major upgrades once identified
            if quality in ["m", "u"] and item_type in (self.profile.preferred_weapons + self.profile.preferred_armor):
                logger.info(f"🎯 Loot: Unidentified {quality}/{item_type} for {self.profile.class_name} - HIGH PRIORITY")
                quality_mult *= 1.5  # Extra boost for unidentified class gear
                high_priority = True  # a real upgrade candidate — make it magnetic

        # Special case: potions in misc
        # If belt is full, lower potion priority
        if item_type == "ms" and empty_belt_slots == 0:
            type_score *= 0.5

        # Special case: prioritize health potions if low HP
        if item_type == "ms" and hp_pct < 50:
            type_score = 0.9  # boost potion value when low HP

        # Distance penalty (closer = better).
        if dist <= 2:
            dist_mult = 1.2
        elif dist <= 5:
            dist_mult = 1.0
        elif dist <= 10:
            dist_mult = 0.8
        else:
            dist_mult = 0.5

        # High-priority class gear (a real upgrade) stays worth walking over for at
        # range — floor the penalty so a distant magic bow doesn't get abandoned —
        # but DON'T boost it. No extra pull means she won't snap to a drop the
        # instant it leaves your hand; she just won't forget it's there.
        if high_priority:
            dist_mult = max(dist_mult, 0.8)

        # Value contribution (normalized)
        # Gold: value is gold amount
        # Items: value is item level * 10
        value_score = 0.0
        if item_type == "go":
            # Gold: 100g = 0.1, 1000g = 1.0
            value_score = min(value / 1000.0, 1.0)
        else:
            # Items: ilvl 10 = 0.1, ilvl 50 = 0.5
            value_score = min(value / 1000.0, 0.8)

        # Combine scores
        score = (type_score * quality_mult * dist_mult) + value_score

        # Gold always gets minimum 0.5 score (always pick up)
        if item_type == "go" and value >= 50:
            score = max(score, 0.5)

        # Bootstrap mode: prioritize gold pickup (need resources!)
        if self.profile and self.profile.bootstrap_mode and item_type == "go":
            score *= 1.5  # 50% boost to gold priority
            logger.debug(f"Loot: Bootstrap mode - boosting gold priority {score:.2f}")

        # Unique items always get high score
        if quality == "u":
            score = max(score, 0.9)

        return score
