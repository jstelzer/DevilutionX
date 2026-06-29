"""
Upgrade Agent - wield better gear.

Closes the loop the other agents set up: Loot picks an item up, Cain identifies
it (magic items must be IDed before they can be judged), and this agent uses the
ItemComparator to decide whether an inventory item beats what she's wearing — and
if so, issues the EQUIP command to swap it in.

EQUIP <inv_slot> is network-correct on the C++ side (AutoEquip + CMD_CHANGEPLRITEMS),
so the swap is a real multiplayer equipment change.
"""

import logging
from typing import Dict, Any, Optional

from .base import BaseAgent, AgentResponse
from item_comparator import ItemComparator

logger = logging.getLogger(__name__)


class UpgradeAgent(BaseAgent):
    """Equips inventory items that beat the currently-worn gear."""

    def __init__(self, **kwargs):
        super().__init__(name="Upgrade", **kwargs)
        # Stop fixating on a "better" item the engine won't actually equip — e.g. a
        # sword whose STR requirement a caster can't meet: AutoEquip fails, the worn
        # gear never changes, and EQUIP <slot> loops forever (Beavis stood still
        # spamming EQUIP 16). Blacklist a slot we keep recommending without it taking.
        self._blacklist = set()
        self._try_slot = None
        self._try_count = 0

    def should_activate(self, state: Dict[str, Any]) -> bool:
        # Don't fiddle with gear mid-fight; need something worn and something to
        # compare it against.
        if state.get("mobs"):
            return False
        return len(state.get("inventory", [])) > 0 and len(state.get("equipped", {})) > 0

    def _is_bad_swap(self, upgrade, state) -> bool:
        """Reject upgrades we should never make. A caster's hand_left staff IS the
        weapon (it casts) — don't trade it for a melee weapon that only scores
        higher on raw damage. Also honor the failed-equip blacklist."""
        candidate = upgrade["candidate"]
        if candidate.get("slot") in self._blacklist:
            return True
        if getattr(self.profile, "is_caster", False):
            worn = (state.get("equipped", {}).get("hand_left") or {}).get("type")
            if upgrade.get("slot") == "hand_left" and worn == "st" and candidate["type"] != "st":
                return True
        return False

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        # Build the comparator with the current class profile so scoring is
        # class-aware (Rogue values bows, Warrior values swords, etc.).
        comparator = ItemComparator(self.profile)
        upgrades = [u for u in comparator.find_upgrades(state) if not self._is_bad_swap(u, state)]
        if not upgrades:
            return None

        best = upgrades[0]  # biggest score_diff first
        candidate = best["candidate"]
        inv_slot = candidate["slot"]
        info = best.get("upgrade_info", {})
        reason = info.get("reason", "better gear")

        # Anti-loop: if we keep recommending the same slot, the equip isn't taking
        # (a real swap would change the inventory and shift the recommendation), so
        # give up on it after a few tries instead of freezing.
        if inv_slot == self._try_slot:
            self._try_count += 1
        else:
            self._try_slot, self._try_count = inv_slot, 1
        if self._try_count > 3:
            self._blacklist.add(inv_slot)
            self._try_slot, self._try_count = None, 0
            logger.warning(f"Upgrade: EQUIP {inv_slot} ({candidate['type']}) isn't taking — blacklisting")
            return None

        logger.info(
            f"🆙 Upgrade: {candidate['type']} ({candidate.get('quality', '?')}) "
            f"-> {best['slot']} (inv slot {inv_slot}): {reason}"
        )
        return AgentResponse(
            command=f"EQUIP {inv_slot}",
            weight=0.7,
            reasoning=f"Upgrade: equip {candidate['type']} to {best['slot']} ({reason})",
        )
