#pragma once
#include <string>
#include <cstdint>

namespace devilution {
class Player;

namespace gap {

/**
 * Encode game state into compact DSL format
 * Format: T=tick F=floor ME=x,y,hp%,mp% M=id@x,y,hp%,flags;... L=id@x,y,value;...
 *
 * This replaces verbose JSON with ~100-200 byte compact representation
 * Benefits:
 *  - 10x smaller on wire
 *  - 5x fewer tokens for LLM
 *  - Faster parsing
 *  - No JSON formatting errors
 */
std::string EncodeDSLState(uint32_t tick, Player* player);

} // namespace gap
} // namespace devilution
