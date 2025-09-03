#pragma once

#include <cstdint>
#include <string>

namespace devilution::gap {

class GapStateExtractor {
public:
    std::string ExtractState(uint32_t tick, uint32_t tick_rate);
    
private:
    std::string ExtractPlayerState();
    std::string ExtractNearbyEntities();
    std::string ExtractUIState();
};

} // namespace devilution::gap