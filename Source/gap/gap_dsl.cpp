#include "gap_dsl.h"
#include <cstdint>
#include "gap_stores.h"
#include "gap_state.h"   // For FindNearbyStairs()
#include "../player.h"
#include "../monster.h"
#include "../items.h"
#include "../objects.h"   // For Objects array and object functions
#include "../diablo.h"
#include "../towners.h"
#include "../spelldat.h"  // For SpellID enum
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

    // Main player position + floor (for companion to follow / decide to transition)
    // If this IS the main player, PLYR will equal ME and PF will equal F.
    if (MyPlayerId < MAX_PLRS && Players[MyPlayerId].plractive) {
        Point mainPlayerPos = Players[MyPlayerId].position.tile;
        dsl << " PLYR=" << mainPlayerPos.x << "," << mainPlayerPos.y;
        dsl << " PF=" << static_cast<int>(Players[MyPlayerId].plrlevel);
    }

    // Nearest stairs/level-transition tile in view: ST=type@x,y (omitted if none).
    // Lets the agent see and path to stairs for level transitions.
    {
        int stairX = 0, stairY = 0;
        std::string stairType = FindNearbyStairs(playerPos.x, playerPos.y, 12, stairX, stairY);
        if (!stairType.empty()) {
            dsl << " ST=" << stairType << "@" << stairX << "," << stairY;
        }
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

    // Objects: OBJ=id@x,y,type;...
    // Types: ch=chest, tc=trapped_chest, dr=door, ba=barrel, sh=shrine
    // Only include objects within light radius for exploration
    std::ostringstream objects;
    bool first_object = true;

    for (int i = 0; i < ActiveObjectCount; i++) {
        const auto& obj = Objects[ActiveObjects[i]];
        Point objPos = obj.position;

        int dx = std::abs(objPos.x - playerPos.x);
        int dy = std::abs(objPos.y - playerPos.y);
        int distance = static_cast<int>(std::sqrt(dx * dx + dy * dy));

        // Only include objects within light radius AND visible
        if (distance <= lightRadius && IsTileLit(objPos)) {
            std::string type_code = "";

            if (obj.IsChest()) {
                type_code = obj.IsTrappedChest() ? "tc" : "ch";
            } else if (obj.isDoor()) {
                type_code = "dr";
            } else if (obj.IsBarrel()) {
                type_code = obj.isExplosive() ? "xb" : "ba";  // xb=explosive barrel
            } else if (obj.IsShrine()) {
                type_code = "sh";
            }

            // Only include interactable objects
            if (!type_code.empty() && obj.canInteractWith()) {
                if (!first_object) objects << ";";
                first_object = false;

                objects << static_cast<int>(ActiveObjects[i]) << "@"
                        << objPos.x << "," << objPos.y << "," << type_code;
            }
        }
    }

    if (!first_object) {
        dsl << " OBJ=" << objects.str();
    }

    // Belt: B=type,type,type,... (8 slots)
    // Types: hp=healing, mp=mana, rj=rejuv, em=empty
    // Scrolls: sh=heal, sp=portal, sr=resurrect, sl=lightning, etc.
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
                    // Encode scroll by spell type
                    switch (belt_item._iSpell) {
                        case SpellID::Healing:      belt << "sh"; break;  // scroll heal
                        case SpellID::TownPortal:   belt << "sp"; break;  // scroll portal
                        case SpellID::Resurrect:    belt << "sr"; break;  // scroll resurrect
                        case SpellID::Lightning:    belt << "sl"; break;  // scroll lightning
                        case SpellID::Fireball:     belt << "sf"; break;  // scroll fireball
                        case SpellID::Identify:     belt << "si"; break;  // scroll identify
                        default:                    belt << "sc"; break;  // scroll generic
                    }
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

    // Inventory: INV=type,type,type,... (40 slots)
    // Only encode non-empty slots as type@slot_index for compactness
    // Types: hp=healing, mp=mana, rj=rejuv, sw=sword, ax=axe, etc.
    // Quality suffix: _m=magic, _u=unique (e.g., sw_m = magic sword)
    std::ostringstream inventory;
    bool first_inv_item = true;
    int inv_count = 0;

    for (int i = 0; i < player->_pNumInv; i++) {
        const auto& inv_item = player->InvList[i];
        if (inv_item.isEmpty()) {
            continue;
        }

        inv_count++;
        if (!first_inv_item) inventory << ";";
        first_inv_item = false;

        // Get item type code
        std::string type_code;
        if (inv_item._itype == ItemType::Misc) {
            // Special handling for potions/scrolls
            switch (inv_item._iMiscId) {
                case IMISC_HEAL:
                case IMISC_FULLHEAL:
                    type_code = "hp";
                    break;
                case IMISC_MANA:
                case IMISC_FULLMANA:
                    type_code = "mp";
                    break;
                case IMISC_REJUV:
                case IMISC_FULLREJUV:
                    type_code = "rj";
                    break;
                case IMISC_SCROLL:
                case IMISC_SCROLLT:
                    // Encode scroll by spell type
                    switch (inv_item._iSpell) {
                        case SpellID::Healing:      type_code = "sh"; break;
                        case SpellID::TownPortal:   type_code = "sp"; break;
                        case SpellID::Resurrect:    type_code = "sr"; break;
                        case SpellID::Identify:     type_code = "si"; break;
                        default:                    type_code = "sc"; break;
                    }
                    break;
                default:
                    type_code = "ms";
                    break;
            }
        } else {
            // Use item type codes (sw, ax, bw, etc.)
            switch (inv_item._itype) {
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
                default:                    type_code = "ms"; break;
            }

            // Add quality suffix for magic/unique items
            if (inv_item._iMagical == ITEM_QUALITY_MAGIC) {
                type_code += "_m";
            } else if (inv_item._iMagical == ITEM_QUALITY_UNIQUE) {
                type_code += "_u";
            }

            // Add identified flag (! = unidentified magic/unique)
            if (!inv_item._iIdentified && inv_item._iMagical != ITEM_QUALITY_NORMAL) {
                type_code += "!";
            }

            // Add stats for identified equipment
            if (inv_item._iIdentified && (inv_item.isWeapon() || inv_item.isArmor() || inv_item.isHelm() || inv_item.isShield())) {
                type_code += ":";

                // Weapons: damage:toHit
                if (inv_item.isWeapon()) {
                    type_code += std::to_string(static_cast<int>(inv_item._iMinDam));
                    type_code += "-";
                    type_code += std::to_string(static_cast<int>(inv_item._iMaxDam));
                    if (inv_item._iPLDam != 0) {
                        type_code += "+";
                        type_code += std::to_string(inv_item._iPLDam);
                    }
                    type_code += ":";
                    type_code += std::to_string(inv_item._iPLToHit);
                }
                // Armor: AC+bonus
                else {
                    type_code += std::to_string(inv_item._iAC + inv_item._iPLAC);
                    int primary_bonus = 0;
                    if (inv_item._iPLStr != 0) primary_bonus = inv_item._iPLStr;
                    else if (inv_item._iPLDex != 0) primary_bonus = inv_item._iPLDex;
                    else if (inv_item._iPLMag != 0) primary_bonus = inv_item._iPLMag;
                    else if (inv_item._iPLVit != 0) primary_bonus = inv_item._iPLVit;

                    if (primary_bonus != 0) {
                        type_code += "+";
                        type_code += std::to_string(primary_bonus);
                    }
                }
            }
        }

        // Format: type@slot_index
        inventory << type_code << "@" << i;
    }

    if (!first_inv_item) {
        dsl << " INV=" << inventory.str();
        dsl << " INVC=" << inv_count;  // Total item count for quick reference
    }

    // Equipped gear: EQ=slot:type,slot:type,...
    // Slots: hd=head, rl=ring_left, rr=ring_right, am=amulet, hl=hand_left, hr=hand_right, ch=chest
    // Example: EQ=hd:hl_m,hl:sw_u,hr:sh,ch:la_m
    // Staves with charges: hl:st_m^12:2 (magic staff with 12 charges of spell ID 2=Firebolt)
    std::ostringstream equipped;
    bool first_equipped = true;

    // Helper lambda to get item type code with stats (for inventory and equipped items)
    auto getItemTypeCodeWithStats = [](const Item& item, bool includeStats = true) -> std::string {
        if (item.isEmpty()) return "";

        std::string type_code;
        if (item._itype == ItemType::Misc) {
            type_code = "ms";
        } else {
            switch (item._itype) {
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
                default:                    type_code = "ms"; break;
            }

            // Add quality suffix
            if (item._iMagical == ITEM_QUALITY_MAGIC) {
                type_code += "_m";
            } else if (item._iMagical == ITEM_QUALITY_UNIQUE) {
                type_code += "_u";
            }

            // Add charges and spell ID suffix for staves (e.g., "st_m^12:2" for 12 charges of Firebolt)
            if (item._itype == ItemType::Staff && item._iCharges > 0) {
                type_code += "^" + std::to_string(item._iCharges);
                type_code += ":" + std::to_string(static_cast<int>(item._iSpell));
            }

            // Add stats for equipment (weapons and armor) if requested
            if (includeStats && (item.isWeapon() || item.isArmor() || item.isHelm() || item.isShield())) {
                type_code += ":";

                // Weapons: damage,toHit,damBonus,durability
                // Format: minDam-maxDam+damBonus:toHit:dur/maxDur
                // Example: "3-6+2:15:45/60" = 3-6 damage, +2 damage bonus, +15 ToHit, 45/60 durability
                if (item.isWeapon()) {
                    type_code += std::to_string(static_cast<int>(item._iMinDam));
                    type_code += "-";
                    type_code += std::to_string(static_cast<int>(item._iMaxDam));
                    if (item._iPLDam != 0) {
                        type_code += "+";
                        type_code += std::to_string(item._iPLDam);
                    }
                    type_code += ":";
                    type_code += std::to_string(item._iPLToHit);

                    // Add durability (except for indestructible items)
                    if (item._iMaxDur > 0 && item._iMaxDur != DUR_INDESTRUCTIBLE) {
                        type_code += ":";
                        type_code += std::to_string(item._iDurability);
                        type_code += "/";
                        type_code += std::to_string(item._iMaxDur);
                    }
                }
                // Armor/Helm/Shield: AC,primaryBonus,durability
                // Format: AC+primaryBonus:dur/maxDur
                // Example: "25+5:40/50" = 25 AC, +5 Str, 40/50 durability
                else {
                    type_code += std::to_string(item._iAC + item._iPLAC);
                    // Add primary stat bonus (prioritize Str > Dex > Mag > Vit)
                    int primary_bonus = 0;
                    if (item._iPLStr != 0) primary_bonus = item._iPLStr;
                    else if (item._iPLDex != 0) primary_bonus = item._iPLDex;
                    else if (item._iPLMag != 0) primary_bonus = item._iPLMag;
                    else if (item._iPLVit != 0) primary_bonus = item._iPLVit;

                    if (primary_bonus != 0) {
                        type_code += "+";
                        type_code += std::to_string(primary_bonus);
                    }

                    // Add durability (except for indestructible items)
                    if (item._iMaxDur > 0 && item._iMaxDur != DUR_INDESTRUCTIBLE) {
                        type_code += ":";
                        type_code += std::to_string(item._iDurability);
                        type_code += "/";
                        type_code += std::to_string(item._iMaxDur);
                    }
                }
            }
        }
        return type_code;
    };

    // Encode each equipped slot
    const char* slot_codes[] = {"hd", "rl", "rr", "am", "hl", "hr", "ch"};
    for (int slot = 0; slot < NUM_INVLOC; slot++) {
        const Item& eq_item = player->InvBody[slot];
        if (eq_item.isEmpty()) continue;

        std::string type_code = getItemTypeCodeWithStats(eq_item, true);  // Include stats
        if (type_code.empty()) continue;

        if (!first_equipped) equipped << ",";
        first_equipped = false;

        equipped << slot_codes[slot] << ":" << type_code;
    }

    if (!first_equipped) {
        dsl << " EQ=" << equipped.str();
    }

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

        // Store inventories (only if companion near vendor)
        // Format: ST_{code}=type/qual/price/id,type/qual/price/id,...
        Point playerPos = player->position.tile;

        // Check if companion is near smith (Griswold)
        for (size_t i = 0; i < NUM_TOWNERS; i++) {
            const auto& towner = Towners[i];
            if (!towner.anim.has_value()) continue;

            // Calculate distance to this NPC
            int dx = std::abs(towner.position.x - playerPos.x);
            int dy = std::abs(towner.position.y - playerPos.y);
            int dist = std::max(dx, dy);  // Chebyshev distance

            // Only show store inventory if within 2 tiles
            if (dist > 2) continue;

            std::vector<StoreItem> storeItems;
            const char* store_code = nullptr;

            switch (towner._ttype) {
            case TOWN_SMITH:
                storeItems = GetStoreInventory(TOWN_SMITH);
                store_code = "sm";
                break;
            case TOWN_HEALER:
                storeItems = GetStoreInventory(TOWN_HEALER);
                store_code = "hl";
                break;
            case TOWN_WITCH:
                storeItems = GetStoreInventory(TOWN_WITCH);
                store_code = "wt";
                break;
            case TOWN_PEGBOY:
                storeItems = GetStoreInventory(TOWN_PEGBOY);
                store_code = "pg";
                break;
            default:
                continue;  // Not a vendor
            }

            if (storeItems.empty()) continue;

            // Encode store inventory
            std::ostringstream store;
            bool first_item = true;

            // Limit to first 10 items to keep DSL compact
            int itemCount = 0;
            for (const auto& item : storeItems) {
                if (itemCount++ >= 10) break;

                if (!first_item) store << ",";
                first_item = false;

                store << item.typeCode << "/"
                      << item.quality << "/"
                      << item.price << "/"
                      << item.itemIndex;
            }

            if (!first_item) {
                dsl << " ST_" << store_code << "=" << store.str();
            }
        }

        // Add companion's gold
        dsl << " GOLD=" << player->_pGold;
    }

    // Note: Could add E= (events) in the future for things like:
    // E=HIT:12,DROP:71,LEVEL_UP,etc.

    return dsl.str();
}

} // namespace devilution::gap
