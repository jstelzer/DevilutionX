#ifdef ENABLE_GAP

#include "actor.h"
#include <cmath>

namespace devilution {

// Base Actor utility methods implementation
int Actor::DistanceTo(const Actor& other) const {
    Point other_pos = other.GetPosition();
    return DistanceTo(other_pos);
}

int Actor::DistanceTo(Point target) const {
    Point my_pos = GetPosition();
    int dx = std::abs(target.x - my_pos.x);
    int dy = std::abs(target.y - my_pos.y);
    return static_cast<int>(std::sqrt(dx * dx + dy * dy));
}

} // namespace devilution

#endif // ENABLE_GAP