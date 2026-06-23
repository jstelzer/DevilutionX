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

    def should_activate(self, state: Dict[str, Any]) -> bool:
        # Don't fiddle with gear mid-fight; need something worn and something to
        # compare it against.
        if state.get("mobs"):
            return False
        return len(state.get("inventory", [])) > 0 and len(state.get("equipped", {})) > 0

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        # Build the comparator with the current class profile so scoring is
        # class-aware (Rogue values bows, Warrior values swords, etc.).
        comparator = ItemComparator(self.profile)
        upgrades = comparator.find_upgrades(state)
        if not upgrades:
            weapons = [(i["type"], i.get("identified"), i.get("stats"))
                       for i in state.get("inventory", [])
                       if i["type"] in ("sw", "ax", "bw", "mc", "st")]
            logger.info(
                f"Upgrade: none. ranged={getattr(self.profile, 'is_ranged', None)} "
                f"equipped_weapon={(state.get('equipped', {}).get('hand_left') or {}).get('type')} "
                f"inv_weapons={weapons}"
            )
            return None

        best = upgrades[0]  # biggest score_diff first
        candidate = best["candidate"]
        inv_slot = candidate["slot"]
        info = best.get("upgrade_info", {})
        reason = info.get("reason", "better gear")

        logger.info(
            f"🆙 Upgrade: {candidate['type']} ({candidate.get('quality', '?')}) "
            f"-> {best['slot']} (inv slot {inv_slot}): {reason}"
        )
        return AgentResponse(
            command=f"EQUIP {inv_slot}",
            weight=0.7,
            reasoning=f"Upgrade: equip {candidate['type']} to {best['slot']} ({reason})",
        )
