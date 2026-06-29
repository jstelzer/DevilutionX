"""
Friendly-fire guard — deterministic line-of-fire geometry shared by the ranged
CombatAgent and the SpellAgent.

The engine already hands us every ally's position (each other player is emitted
as its own `PLYR=` in the DSL → `state["allies"]`). A ranged shot / aimed spell
travels in a straight line from the shooter to the target tile, so a projectile
passes through any ally sitting on that segment. Rather than ask the LLM to
reason about it, we just don't take a shot that runs through a friend: retarget
to a clear monster, or sidestep to open the angle.
"""

import math
from typing import List, Optional, Sequence, Tuple

Pt = Tuple[int, int]

# How close (in tiles) an ally has to be to the shot line to count as "in the way".
# A projectile is ~1 tile wide; the 0.79-of-shots friendly-fire run that motivated
# this used the same 1.0 threshold.
LOF_MARGIN = 1.0


def _dist_to_segment(ax, ay, bx, by, px, py) -> Tuple[float, float]:
    """Perpendicular distance from P to segment A→B, and the projection param t
    (0 = at A/shooter, 1 = at B/target)."""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - ax, py - ay), 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / l2
    tc = max(0.0, min(1.0, t))
    cx, cy = ax + tc * dx, ay + tc * dy
    return math.hypot(px - cx, py - cy), t


def shot_blocked(shooter: Pt, target: Pt, allies: Sequence[Pt],
                 margin: float = LOF_MARGIN) -> bool:
    """True if any ally is within `margin` of the shooter→target line AND between
    them (so a projectile would clip the ally). Allies essentially on the shooter's
    own tile (t≈0) or the target's tile (t≈1) are ignored."""
    ax, ay = shooter
    bx, by = target
    for px, py in allies:
        d, t = _dist_to_segment(ax, ay, bx, by, px, py)
        if d <= margin and 0.05 < t < 0.95:
            return True
    return False


def clear_mobs(shooter: Pt, mobs: list, allies: Sequence[Pt],
               margin: float = LOF_MARGIN) -> list:
    """Subset of `mobs` we can fire at without an ally in the line."""
    if not allies:
        return list(mobs)
    return [m for m in mobs
            if not shot_blocked(shooter, (m.get("x", 0), m.get("y", 0)), allies, margin)]


def sidestep(shooter: Pt, target: Pt, allies: Sequence[Pt],
             margin: float = LOF_MARGIN) -> Optional[Pt]:
    """A tile one or two steps perpendicular to the shot line that opens a clear
    angle on `target`, or None if a small sidestep doesn't help."""
    ax, ay = shooter
    bx, by = target
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length == 0:
        return None
    perp = (-dy / length, dx / length)  # unit perpendicular
    # Try increasingly large flanking steps. An ally near the target end of the
    # line barely moves relative to the shot when we step a tile, so a clear angle
    # can need several tiles of offset — but prefer the smallest that works.
    for step in range(1, 6):
        for sign in (1, -1):
            nx = int(round(ax + sign * perp[0] * step))
            ny = int(round(ay + sign * perp[1] * step))
            if (nx, ny) != (ax, ay) and not shot_blocked((nx, ny), target, allies, margin):
                return (nx, ny)
    return None


def allies_of(state) -> List[Pt]:
    """All ally tiles from state — the full PLYR= list, or the single follow
    target as a fallback for older parses."""
    allies = state.get("allies")
    if allies:
        return list(allies)
    player = state.get("player")
    return [player] if player else []
