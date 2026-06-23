"""
Extraction Agent — the PortalCapability: open and use a town portal to escape.

This is the *producer* side of portals (PortalAgent is the *consumer* that
follows the human's). The provider model is pluggable: today it's scroll-based
(a Town Portal scroll, belt code 'sp', cast via `CS <slot>`); a spell-based
provider can be added once known spells reach the DSL. The trigger today is
survival — when she's likely to die (low HP with no healing to recover) and
there's no human portal to flee through, she opens her own and steps to town.

Coordination invariants honored here (what a party-protocol spec would check):
- Ownership is unambiguous: this agent only ever creates/uses HER OWN ('me')
  portal; 'them' portals belong to PortalAgent. One owner per portal.
- No stranding: she opens a portal only when no human portal exists, and she
  crosses her own (which closes on her crossing). The human isn't relying on it,
  so going first strands nobody. (Inviting the human through her portal would
  need the go-first/hold dance PortalAgent already does — a later step.)
- Liveness: when doomed and able, there is always a legal action (cast, then
  step), so she never stalls dying with a scroll in hand.
- No yo-yo: every action is gated on STILL needing extraction, so a stale 'me'
  portal can't pull a healthy companion back to town.
"""

import logging
from typing import Dict, Any, Optional

from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class ExtractionAgent(BaseAgent):
    """Creates and uses a town portal to self-extract when in danger."""

    DOOMED_HP = 35  # at/below this HP%, with no healing, she needs to escape

    def __init__(self, **kwargs):
        super().__init__(name="Extraction", **kwargs)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        if state.get("in_town"):
            return False
        if not self._needs_extraction(state):
            return False
        # Active only if we can act on it: a portal already open, a scroll to open
        # one, or the Town Portal spell known with enough mana.
        tp = self._town_portal_spell(state)
        return (self._my_portal(state) is not None
                or self._portal_scroll_slot(state) is not None
                or (tp is not None and tp.get("affordable")))

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        hp_pct = state.get("me", [0, 0, 100, 100])[2]

        # If our portal is already open, step into it to escape to town.
        portal = self._my_portal(state)
        if portal is not None:
            px, py = portal["x"], portal["y"]
            logger.info(f"Extraction: stepping into my town portal at ({px},{py}) to escape (HP={hp_pct}%)")
            return AgentResponse(
                command=f"MV {px} {py}",
                weight=0.9,
                reasoning=f"Extraction: through my own portal to town (HP={hp_pct}%)",
            )

        # No portal yet — open one. Prefer a scroll (CS casts from belt) so we
        # don't burn mana we might still need; fall back to the spell.
        slot = self._portal_scroll_slot(state)
        if slot is not None:
            logger.info(f"Extraction: doomed (HP={hp_pct}%, no healing) — casting Town Portal scroll (belt slot {slot})")
            return AgentResponse(
                command=f"CS {slot}",
                weight=0.9,
                reasoning=f"Extraction: open town portal via scroll (HP={hp_pct}%, no healing)",
            )

        tp = self._town_portal_spell(state)
        if tp is not None and tp.get("affordable"):
            me = state.get("me", [0, 0, 100, 100])
            mx, my = me[0], me[1]
            logger.info(f"Extraction: doomed (HP={hp_pct}%) — casting {tp['name']} (spell {tp['id']})")
            return AgentResponse(
                command=f"CAST {tp['id']} {mx} {my}",
                weight=0.9,
                reasoning=f"Extraction: open town portal via spell (HP={hp_pct}%, no healing)",
            )

        return None

    # --- PortalCapability helpers / providers -----------------------------

    def _my_portal(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Our own open town portal, if any ('me' caster)."""
        for p in (state.get("portals") or []):
            if p.get("caster") == "me":
                return p
        return None

    def _portal_scroll_slot(self, state: Dict[str, Any]) -> Optional[int]:
        """Belt slot of a Town Portal scroll ('sp'), or None. Scroll provider:
        CS casts from the belt, so the scroll must be belted to be usable."""
        for i, item in enumerate(state.get("belt", [])):
            if item == "sp":
                return i
        return None

    def _town_portal_spell(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Spell provider: the known Town Portal spell from the engine's menu
        (matched by name, so no hard-coded id), or None."""
        for s in state.get("spells", []):
            if s.get("name", "").lower() == "town portal":
                return s
        return None

    def _needs_extraction(self, state: Dict[str, Any]) -> bool:
        """True when she's likely to die here and can't recover on the spot."""
        # A human portal already here? PortalAgent flees through it — defer.
        if any(p.get("caster") == "them" for p in (state.get("portals") or [])):
            return False
        hp_pct = state.get("me", [0, 0, 100, 100])[2]
        if hp_pct > self.DOOMED_HP:
            return False
        # Can we still recover where we stand? Healing in belt or pack -> heal /
        # refill instead of fleeing.
        if any(s in ("hp", "rj") for s in state.get("belt", [])):
            return False
        if any(it.get("type") in ("hp", "rj") for it in state.get("inventory", [])):
            return False
        return True
