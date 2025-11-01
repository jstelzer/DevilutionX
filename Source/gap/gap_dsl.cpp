#include "gap_dsl.h"
#include "../player.h"
#include "../monster.h"
#include "../items.h"
#include "../diablo.h"
#include <sstream>
#include <cmath>

namespace devilution::gap {

std::string EncodeDSLState(uint32_t tick, Player* player) {
    if (player == nullptr) {
        return "";
    }

    std::ostringstream dsl;

    // Basic state: T=tick F=floor ME=x,y,hp%,mp%
    Point playerPos = player->position.tile;
    int hp_pct = (player->_pHitPoints >> 6) * 100 / std::max(1, (player->_pMaxHP >> 6));
    int mp_pct = (player->_pMana >> 6) * 100 / std::max(1, (player->_pMaxMana >> 6));

    dsl << "T=" << tick
        << " F=" << static_cast<int>(currlevel)
        << " ME=" << playerPos.x << "," << playerPos.y << "," << hp_pct << "," << mp_pct;

    // Main player position (for companion to follow)
    // If this IS the main player, PLYR will equal ME
    if (MyPlayerId < MAX_PLRS && Players[MyPlayerId].plractive) {
        Point mainPlayerPos = Players[MyPlayerId].position.tile;
        dsl << " PLYR=" << mainPlayerPos.x << "," << mainPlayerPos.y;
    }

    // Monsters: M=id@x,y,hp%,flags;...
    std::ostringstream monsters;
    bool first_monster = true;
    int lightRadius = player->_pLightRad > 0 ? player->_pLightRad : 10;

    for (size_t i = 0; i < ActiveMonsterCount; i++) {
        const auto& monster = Monsters[ActiveMonsters[i]];

        // Skip dead monsters
        if (monster.hitPoints <= 0) {
            continue;
        }

        Point monsterPos = monster.position.tile;

        int dx = std::abs(monsterPos.x - playerPos.x);
        int dy = std::abs(monsterPos.y - playerPos.y);
        int distance = static_cast<int>(std::sqrt(dx * dx + dy * dy));

        // Only include monsters within light radius
        if (distance <= lightRadius) {
            if (!first_monster) monsters << ";";
            first_monster = false;

            int hp_pct = monster.hitPoints * 100 / std::max(1, monster.maxHitPoints);

            // Build flags bitfield
            // 1 (0x01) = hostile/attacking
            // 2 (0x02) = unique
            // 4 (0x04) = ranged (using mode as heuristic)
            // 8 (0x08) = elite (reserved for future)
            uint32_t flags = 0;
            if (monster.goal == MonsterGoal::Attack) flags |= 1;  // hostile
            if (monster.isUnique()) flags |= 2;                   // unique
            // Detect ranged by checking if monster is in ranged attack mode
            if (monster.mode == MonsterMode::RangedAttack ||
                monster.mode == MonsterMode::SpecialRangedAttack) {
                flags |= 4;  // ranged
            }

            monsters << ActiveMonsters[i] << "@"
                     << monsterPos.x << "," << monsterPos.y << ","
                     << hp_pct << "," << flags;
        }
    }

    if (!first_monster) {
        dsl << " M=" << monsters.str();
    }

    // Items: L=id@x,y,value;...
    std::ostringstream items;
    bool first_item = true;

    for (int i = 0; i < ActiveItemCount; i++) {
        const auto& item = Items[ActiveItems[i]];
        Point itemPos = item.position;

        int dx = std::abs(itemPos.x - playerPos.x);
        int dy = std::abs(itemPos.y - playerPos.y);
        int distance = static_cast<int>(std::sqrt(dx * dx + dy * dy));

        // Only include items within light radius
        if (distance <= lightRadius) {
            if (!first_item) items << ";";
            first_item = false;

            // Heuristic value: gold value, or item level for other items
            int value = item._itype == ItemType::Gold ? item._ivalue : item._iIvalue * 10;

            // Cast to int to avoid uint8_t being treated as char
            items << static_cast<int>(ActiveItems[i]) << "@"
                  << itemPos.x << "," << itemPos.y << ","
                  << value;
        }
    }

    if (!first_item) {
        dsl << " L=" << items.str();
    }

    // Note: Could add E= (events) in the future for things like:
    // E=HIT:12,DROP:71,LEVEL_UP,etc.

    return dsl.str();
}

} // namespace devilution::gap
