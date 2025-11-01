#include "gap_dsl.h"
#include "../player.h"
#include "../monster.h"
#include "../items.h"
#include "../diablo.h"
#include "../towners.h"
#include "../levels/gendung.h"  // For IsTileLit()
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

    // Stats: S=str,dex,mag,vit,lvl,pts,class,exp
    // Class codes: 0=warrior, 1=rogue, 2=sorc, 3=monk, 4=bard, 5=barb
    dsl << " S=" << player->_pStrength
        << "," << player->_pDexterity
        << "," << player->_pMagic
        << "," << player->_pVitality
        << "," << static_cast<int>(player->getCharacterLevel())
        << "," << player->_pStatPts
        << "," << static_cast<int>(player->_pClass)
        << "," << player->_pExperience;

    // Town flag: TN=1 or TN=0
    dsl << " TN=" << (leveltype == DTYPE_TOWN ? 1 : 0);

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

        // Only include monsters within light radius AND actually visible (line-of-sight check)
        // IsTileLit() checks if tile is lit, accounting for walls/obstacles
        if (distance <= lightRadius && IsTileLit(monsterPos)) {
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

    // Items: L=id@x,y,value,type,qual;...
    // Type codes: go=gold, sw=sword, ax=axe, bw=bow, mc=mace, sh=shield,
    //             la/ma/ha=armor, hl=helm, st=staff, rg=ring, am=amulet, ms=misc
    // Quality codes: n=normal, m=magic, u=unique
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

            // Encode item type
            const char* type_code;
            switch (item._itype) {
                case ItemType::Gold:        type_code = "go"; break;
                case ItemType::Sword:       type_code = "sw"; break;
                case ItemType::Axe:         type_code = "ax"; break;
                case ItemType::Bow:         type_code = "bw"; break;
                case ItemType::Mace:        type_code = "mc"; break;
                case ItemType::Shield:      type_code = "sh"; break;
                case ItemType::LightArmor:  type_code = "la"; break;
                case ItemType::MediumArmor: type_code = "ma"; break;
                case ItemType::HeavyArmor:  type_code = "ha"; break;
                case ItemType::Helm:        type_code = "hl"; break;
                case ItemType::Staff:       type_code = "st"; break;
                case ItemType::Ring:        type_code = "rg"; break;
                case ItemType::Amulet:      type_code = "am"; break;
                default:                    type_code = "ms"; break; // misc/other
            }

            // Encode quality
            char qual_code;
            switch (item._iMagical) {
                case ITEM_QUALITY_MAGIC:  qual_code = 'm'; break;
                case ITEM_QUALITY_UNIQUE: qual_code = 'u'; break;
                default:                  qual_code = 'n'; break; // normal
            }

            // Cast to int to avoid uint8_t being treated as char
            items << static_cast<int>(ActiveItems[i]) << "@"
                  << itemPos.x << "," << itemPos.y << ","
                  << value << "," << type_code << "," << qual_code;
        }
    }

    if (!first_item) {
        dsl << " L=" << items.str();
    }

    // Belt: B=type,type,type,... (8 slots)
    // Types: hp=healing, mp=mana, rj=rejuv, sc=scroll, em=empty
    std::ostringstream belt;
    for (int i = 0; i < MaxBeltItems; i++) {
        if (i > 0) belt << ",";

        const auto& belt_item = player->SpdList[i];
        if (belt_item.isEmpty()) {
            belt << "em";
        } else if (belt_item._itype == ItemType::Misc) {
            switch (belt_item._iMiscId) {
                case IMISC_HEAL:
                case IMISC_FULLHEAL:
                    belt << "hp";
                    break;
                case IMISC_MANA:
                case IMISC_FULLMANA:
                    belt << "mp";
                    break;
                case IMISC_REJUV:
                case IMISC_FULLREJUV:
                    belt << "rj";
                    break;
                case IMISC_SCROLL:
                case IMISC_SCROLLT:
                    belt << "sc";
                    break;
                default:
                    belt << "ms";  // misc
                    break;
            }
        } else {
            belt << "ms";  // misc (non-potion item)
        }
    }
    dsl << " B=" << belt.str();

    // NPCs (only in town): NPC=type@x,y;type@x,y;...
    // Type codes: sm=Smith, hl=Healer, wt=Witch, tv=Tavern, st=Storyteller, etc.
    if (leveltype == DTYPE_TOWN) {
        std::ostringstream npcs;
        bool first_npc = true;

        for (size_t i = 0; i < NUM_TOWNERS; i++) {
            const auto& towner = Towners[i];

            // Skip uninitialized towners (they don't have an anim)
            if (!towner.anim.has_value()) {
                continue;
            }

            // Map towner type to code
            const char* type_code;
            switch (towner._ttype) {
                case TOWN_SMITH:   type_code = "sm"; break;  // Griswold the Blacksmith
                case TOWN_HEALER:  type_code = "hl"; break;  // Pepin the Healer
                case TOWN_DEADGUY: type_code = "dg"; break;  // Wounded Townsman
                case TOWN_TAVERN:  type_code = "tv"; break;  // Ogden the Tavern owner
                case TOWN_STORY:   type_code = "cn"; break;  // Cain the Elder
                case TOWN_DRUNK:   type_code = "dr"; break;  // Farnham the Drunk
                case TOWN_WITCH:   type_code = "wt"; break;  // Adria the Witch
                case TOWN_BMAID:   type_code = "bm"; break;  // Gillian the Barmaid
                case TOWN_PEGBOY:  type_code = "pg"; break;  // Wirt the Peg-legged boy
                case TOWN_COW:     type_code = "cw"; break;  // Cow
                case TOWN_FARMER:  type_code = "fm"; break;  // Lester the farmer
                case TOWN_GIRL:    type_code = "gl"; break;  // Celia
                case TOWN_COWFARM: type_code = "cf"; break;  // Complete Nut (Cowfarm)
                default:           type_code = "npc"; break; // Generic/Unknown
            }

            if (!first_npc) npcs << ";";
            first_npc = false;

            npcs << type_code << "@"
                 << towner.position.x << "," << towner.position.y
                 << "," << static_cast<int>(i);  // Include index for IN command
        }

        if (!first_npc) {
            dsl << " NPC=" << npcs.str();
        }
    }

    // Note: Could add E= (events) in the future for things like:
    // E=HIT:12,DROP:71,LEVEL_UP,etc.

    return dsl.str();
}

} // namespace devilution::gap
