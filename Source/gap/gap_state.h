#pragma once

#include <cstdint>
#include <string>

// Toggle between JSON and DSL state encoding
// Set to 1 to use compact DSL format (100-200 bytes)
// Set to 0 to use verbose JSON format (1-2KB)
#ifndef GAP_USE_DSL
#define GAP_USE_DSL 1
#endif

namespace devilution::gap {

// Find the nearest stairs/level-transition tile within `radius` of (cx,cy) on
// the current level. Returns the stair type string ("down_next", "up_town", …)
// and sets outX/outY, or "" if none. Shared by the JSON and DSL state encoders.
std::string FindNearbyStairs(int cx, int cy, int radius, int &outX, int &outY);

class GapStateExtractor {
public:
    std::string ExtractState(uint32_t tick, uint32_t tick_rate);

    // DSL version - compact state representation
    std::string ExtractStateDSL(uint32_t tick, uint32_t tick_rate);

private:
    std::string ExtractPlayerState();
    std::string ExtractNearbyEntities();
    std::string ExtractUIState();
};

} // namespace devilution::gap