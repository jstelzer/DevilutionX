"""
llm_view — the single bouncer between rich game state and LLM prompts.

Principle (the guard the project asked for): the DSL and the hydrated Python
state may be arbitrarily rich — gear footprints, per-item `fits` flags, the
spell->id map, exact mana costs, durability numbers. Deterministic Python tactics
feed on all of that. The **LLM**, by contrast, gets ONLY lean, decision-relevant
*conclusions* — never the raw metadata. Dumping the whole state into an Ollama
prompt is what blew the context window before and sent it sideways.

This module is the one place game state is shaped for a prompt. Each section
builder is an explicit whitelist: it constructs exactly what the LLM may see.
Agents MUST source prompt context from `llm_view(state, ...)` and must never
serialize the raw state dict (or a namespace of it) into a prompt.

    ctx = llm_view(state, "self", "threats")
    # ctx == {"self": {...lean...}, "threats": [{...lean...}, ...]}
"""

from typing import Dict, Any, List

# Class index (from the DSL S= field) -> readable name. The LLM thinks in names.
_CLASS_NAMES = ["Warrior", "Rogue", "Sorcerer", "Monk", "Bard", "Barbarian"]


def _pack_phrase(state: Dict[str, Any]) -> str:
    """Inventory fullness as a CONCLUSION, by grid area — never footprints/cells
    lists. 40-cell grid (10x4)."""
    free = state.get("inv_free", 40)
    if free <= 2:
        return "pack full"
    if free <= 8:
        return "pack nearly full"
    if free <= 20:
        return "some pack space"
    return "plenty of pack space"


def _self(state: Dict[str, Any]) -> Dict[str, Any]:
    me = state.get("me", [0, 0, 100, 100])
    stats = state.get("stats") or {}
    cls = stats.get("class")
    return {
        "hp_pct": me[2] if len(me) > 2 else 100,
        "mp_pct": me[3] if len(me) > 3 else 100,
        "pos": [me[0], me[1]] if len(me) >= 2 else [0, 0],
        "class": _CLASS_NAMES[cls] if isinstance(cls, int) and 0 <= cls < len(_CLASS_NAMES) else None,
        "in_town": bool(state.get("in_town")),
        "pack": _pack_phrase(state),
    }


def _threats(state: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    """Lean monster list for target selection: id/pos/dist/hp + a threat kind.
    Decision-relevant (the LLM picks a target id) — NOT raw flag bitfields."""
    out = []
    for mob in state.get("mobs", [])[:limit]:
        flags = mob.get("flags", 0)
        kind = "boss" if (flags & 2) else ("archer" if (flags & 4) else "melee")
        out.append({
            "id": mob.get("id", 0),
            "pos": [mob.get("x", 0), mob.get("y", 0)],
            "dist": mob.get("dist", 999),
            "hp_pct": mob.get("hp_pct", mob.get("hp%", 100)),
            "kind": kind,
        })
    return out


def _loot(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Nearby loot as phrases — name-ish type, value, and the `fits` conclusion
    (never footprints). Top few by value."""
    items = sorted(state.get("loot", []), key=lambda it: it.get("value", 0), reverse=True)
    return [{
        "type": it.get("type", "ms"),
        "quality": it.get("quality", "n"),
        "value": it.get("value", 0),
        "dist": it.get("dist", 999),
        "fits": bool(it.get("fits", True)),
    } for it in items[:5]]


# The whitelist: the ONLY sections the LLM can ever receive.
_SECTIONS = {
    "self": _self,
    "threats": _threats,
    "loot": _loot,
}


def llm_view(state: Dict[str, Any], *sections: str) -> Dict[str, Any]:
    """Project rich state down to the whitelisted, LLM-safe view for the named
    sections. Unknown sections are ignored (fail-closed: nothing leaks)."""
    return {s: _SECTIONS[s](state) for s in sections if s in _SECTIONS}
