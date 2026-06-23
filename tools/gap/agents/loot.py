"""
Loot Agent - Item evaluation and pickup specialist
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class LootAgent(BaseAgent):
    """Specialist for item evaluation and pickup decisions"""

    # Make-room: when a magic/unique find won't fit the grid (engine `fits`
    # flag), drop junk to free space. Drop at most once per cooldown so the
    # engine has time to recompute fit before we drop again.
    MAKE_ROOM_COOLDOWN = 20
    # Equipment types we're willing to drop as junk to make room (same set the
    # Griswold agent treats as sellable). Never potions/scrolls/misc.
    SELLABLE_TYPES = ("sw", "ax", "bw", "mc", "sh", "la", "ma", "ha", "hl", "st")

    def __init__(self, **kwargs):
        super().__init__(name="Loot", **kwargs)
        self.failed_pickups = {}  # item_id -> attempt_count
        self.last_loot_state = []  # Track items from last tick
        self.last_pk_attempt = None  # item_id we actually issued PK for last tick
        self.recently_dropped = {}  # item_position -> tick_when_dropped (avoid picking up what we just dropped)
        self._made_room_tick = -999  # last tick we dropped junk to make room
        # Unreachable-loot detection: if we keep issuing MV toward the same item
        # but our position doesn't change, the tile can't be pathed to — give up
        # on it (a high-value magic item in a walled-off spot otherwise freezes us).
        self._mv_target = None   # item id we're walking toward
        self._mv_last_pos = None  # our pos when we started walking to it
        self._mv_stuck = 0       # ticks with no progress toward it

    STUCK_GIVEUP = 8  # MV ticks with zero movement before blacklisting the item

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
            here = (me_x, me_y)
            if item_id == self._mv_target and here == self._mv_last_pos:
                # Same target, didn't move since last MV → can't path there.
                self._mv_stuck += 1
                if self._mv_stuck >= self.STUCK_GIVEUP:
                    self.failed_pickups[item_id] = 3  # blacklist as unreachable
                    logger.warning(
                        f"Loot: can't reach {item_desc} at ({item_x},{item_y}) from {here} "
                        f"after {self._mv_stuck} ticks - blacklisting as unreachable"
                    )
                    self._mv_target = None
                    self._mv_stuck = 0
                    return AgentResponse(command="NONE", weight=0.0,
                                         reasoning=f"Loot: {item_desc} unreachable - giving up")
            else:
                # New target or we made progress — reset the stuck counter.
                self._mv_target = item_id
                self._mv_stuck = 0
            self._mv_last_pos = here
            return AgentResponse(
                command=f"MV {item_x} {item_y}",
                weight=min(best_score, 1.0),
                reasoning=f"Loot: Moving to {item_desc} value={best_item.get('value', 0)} dist={item_dist}"
            )

        # MAKE ROOM: the engine tells us per-item whether it actually fits the
        # grid right now (`fits`). If a wanted find doesn't fit, drop junk to free
        # space instead of the pick-up-then-drop-back loop. We drop the bulkiest
        # junk (most cells) and let the engine recompute `fits` next tick — no
        # tetris guessing here. Gold/potions always fit (engine says so).
        if not best_item.get("fits", True):
            if current_tick - self._made_room_tick >= self.MAKE_ROOM_COOLDOWN:
                junk = self._pick_junk_to_drop(state)
                if junk is not None:
                    junk_slot, junk_desc = junk
                    self._made_room_tick = current_tick
                    logger.info(
                        f"Loot: {item_desc} doesn't fit (free={state.get('inv_free', '?')} cells) "
                        f"- dropping junk {junk_desc} (slot {junk_slot}) to make room"
                    )
                    return AgentResponse(
                        command=f"DROP {junk_slot}",
                        weight=min(best_score, 1.0),
                        reasoning=f"Loot: make room (drop {junk_desc}) for {item_desc}"
                    )
            # Doesn't fit and no junk to sacrifice (or on cooldown) — don't spam
            # PK on something that can't be placed; let another agent act.
            return AgentResponse(
                command="NONE", weight=0.0,
                reasoning=f"Loot: {item_desc} won't fit and no junk to drop"
            )

        # Item is adjacent and fits - pick it up. Record the real attempt so we
        # can tell next tick whether the PK actually worked.
        self.last_pk_attempt = item_id
        return AgentResponse(
            command=f"PK {item_id}",
            weight=min(best_score, 1.0),
            reasoning=f"Loot: Pickup {item_desc} value={best_item.get('value', 0)} dist={item_dist}"
        )

    def _pick_junk_to_drop(self, state: Dict[str, Any]) -> Optional[tuple]:
        """Pick the least-valuable droppable junk to free a slot for a find.

        Junk = identified equipment the profile doesn't want (or, with no
        profile, normal quality). Never drops potions, scrolls, misc, or
        unidentified items (could be good once IDed). Prefers to sacrifice the
        BULKIEST junk (most grid cells) so a single drop is most likely to open
        room for the find, tie-broken by lowest quality. Returns (slot, desc).
        """
        quality_rank = {"normal": 0, "n": 0, "magic": 1, "m": 1, "unique": 2, "u": 2}
        candidates = []
        for item in state.get("inventory", []):
            if item.get("type") not in self.SELLABLE_TYPES:
                continue
            if not item.get("identified"):
                continue  # don't toss something we haven't IDed yet
            quality = item.get("quality", "normal")
            if self.profile:
                if self.profile.should_keep_item(item["type"], quality).get("keep"):
                    continue  # class-appropriate gear we'd want — keep it
            elif quality not in ("normal", "n"):
                continue  # no profile: only ever drop plain normal gear
            candidates.append(item)

        if not candidates:
            return None

        # Bulkiest first (most cells freed), then lowest quality.
        candidates.sort(key=lambda it: (-it.get("cells", 1),
                                        quality_rank.get(it.get("quality", "normal"), 0)))
        junk = candidates[0]
        return junk.get("slot"), f"{junk.get('quality', 'n')}/{junk.get('type')}"

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

        # If the engine says it won't fit the grid, only a magic/unique find is
        # worth dropping junk for — ignore non-fitting normal gear entirely so we
        # don't loop trying to grab something we can't place (and would just
        # drop back). Gold/potions always report fits=True.
        if not item.get("fits", True) and quality not in ("m", "u"):
            return 0.0

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
