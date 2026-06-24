"""
Hazard-layer helpers — the "see the fire" utilities.

The DSL emits an ``HZ=x,y,kind`` layer (active hostile missiles / AoE tiles near
us; see ``gap_dsl.cpp`` and ``dsl_parser.py``). These helpers turn that raw list
into the two questions tactics actually ask: "is this tile dangerous?" and
"where's the nearest tile that isn't?". Pure geometry, no engine knowledge.

Distances here are CHEBYSHEV (king moves): a hazard "covers" its own tile plus a
``radius``-ring around it, because AoE splashes and a fast missile may arrive on
an adjacent tile next tick. Keep this conservative — a false dodge is cheap, a
missed one costs HP.
"""

from typing import Any, Dict, List, Optional, Tuple


def hazards_within(state: Dict[str, Any], x: int, y: int, radius: int = 1) -> List[Dict[str, Any]]:
    """Hazard entries whose tile is within Chebyshev ``radius`` of (x, y)."""
    out = []
    for hz in state.get("hazards", []):
        if abs(hz["x"] - x) <= radius and abs(hz["y"] - y) <= radius:
            out.append(hz)
    return out


def is_tile_dangerous(state: Dict[str, Any], x: int, y: int, radius: int = 1) -> bool:
    """True if any active hazard covers (x, y) within ``radius``."""
    return bool(hazards_within(state, x, y, radius))


def standing_in_hazard(state: Dict[str, Any], radius: int = 1) -> bool:
    """True if our own tile is in/adjacent to a hazard (the reflex trigger)."""
    me_x, me_y, _, _ = state.get("me", [0, 0, 100, 100])
    return is_tile_dangerous(state, me_x, me_y, radius)


def nearest_safe_tile(
    state: Dict[str, Any],
    prefer: Optional[Tuple[int, int]] = None,
    search: int = 5,
    radius: int = 1,
) -> Optional[Tuple[int, int]]:
    """Closest tile to ME (within a ``search``-box) that no hazard covers.

    Picks the fewest-steps-away safe tile; ``prefer`` (e.g. the human's position)
    breaks ties so she steps out of the fire *toward the party*, not off alone
    into the dark. Returns None if every reachable tile in range is dangerous
    (boxed in) — the caller decides what to do then.
    """
    me_x, me_y, _, _ = state.get("me", [0, 0, 100, 100])
    if not state.get("hazards"):
        return None

    best: Optional[Tuple[int, int]] = None
    best_key: Optional[Tuple[int, int]] = None
    for dx in range(-search, search + 1):
        for dy in range(-search, search + 1):
            if dx == 0 and dy == 0:
                continue  # current tile — we only get here because it's unsafe
            tx, ty = me_x + dx, me_y + dy
            if tx < 0 or ty < 0:
                continue
            if is_tile_dangerous(state, tx, ty, radius):
                continue
            step = max(abs(dx), abs(dy))  # Chebyshev: cost to walk there
            bias = (abs(tx - prefer[0]) + abs(ty - prefer[1])) if prefer else 0
            key = (step, bias)
            if best_key is None or key < best_key:
                best_key, best = key, (tx, ty)
    return best
