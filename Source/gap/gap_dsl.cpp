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
#include "../spelldat.h"  // For SpellID enum / GetSpellData
#include "../spells.h"    // For GetManaAmount
#include "../inv.h"       // For CanFitItemInInventory / CanBePlacedOnBelt / GetInventorySize
#include "../levels/gendung.h"  // For IsTileLit()
#include "../levels/trigs.h"    // For trigs[] (real level-transition tiles)
#include "../interfac.h"        // For WM_DIAB* interface_mode values
#include "../missiles.h"        // For Missiles (town portal detection)
#include "../misdat.h"          // For MissileID::TownPortal
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

    // Hero name (N=). Static per session, but emitted on every line so each state
    // line — and every recorded trace line — is self-describing: it says which
    // toon produced it. That becomes the source_id for agent logs and the HUD,
    // disambiguating multiple AI clients (Airhead vs Beavis) without side state.
    // Spaces -> '_' (same convention as spell names below); empty -> '?'.
    {
        std::string name = player->_pName;
        for (char &c : name) if (c == ' ') c = '_';
        if (name.empty()) name = "?";
        dsl << " N=" << name;
    }

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

    // Every OTHER active player gets a PLYR=/PF= pair (the human AND any other AI
    // companions). The FIRST is the follow target (player 0 = the human host); the
    // full set feeds the friendly-fire line-of-fire guard so the AIs don't shoot
    // each other either. PLYR/PF are omitted if we're the only one in the game.
    for (size_t i = 0; i < Players.size(); i++) {
        if (static_cast<int>(i) == MyPlayerId || !Players[i].plractive)
            continue;
        Point otherPos = Players[i].position.tile;
        dsl << " PLYR=" << otherPos.x << "," << otherPos.y;
        dsl << " PF=" << static_cast<int>(Players[i].plrlevel);
    }

    // Level-transition triggers: ST=<dir>@x,y;<dir>@x,y;... (omitted if none).
    // These are the REAL trigger tiles from trigs[] (the engine fires the level
    // change when MyPlayer stands on one), not the offset stair graphic. We emit
    // all of them with a direction so the agent can pick the one matching where
    // the player went.
    {
        std::ostringstream stairs;
        bool first = true;
        for (int i = 0; i < numtrigs; i++) {
            const char* dir = nullptr;
            switch (trigs[i]._tmsg) {
            case WM_DIABNEXTLVL:
                dir = "down";  // normal step down one level
                break;
            case WM_DIABPREVLVL:
            case WM_DIABRTNLVL:
            case WM_DIABTWARPUP:
                dir = "up";  // step up one level / return to town
                break;
            case WM_DIABTOWNWARP:
                dir = "warp";  // town shortcut to a *specific* deeper dungeon
                break;
            default:
                break;
            }
            if (dir == nullptr)
                continue;
            if (!first)
                stairs << ";";
            stairs << dir << "@" << static_cast<int>(trigs[i].position.x)
                   << "," << static_cast<int>(trigs[i].position.y);
            first = false;
        }
        if (!first)
            dsl << " ST=" << stairs.str();
    }

    // Active town portals: TP=x,y,caster;... A portal closes when its caster
    // steps through, so we emit the caster slot — the agent uses it to decide
    // who goes first (rush through someone else's portal; let them go first
    // through ours).
    {
        std::ostringstream portals;
        bool first = true;
        for (auto &missile : Missiles) {
            if (missile._mitype != MissileID::TownPortal)
                continue;
            if (!first)
                portals << ";";
            // Relative caster so the agent can apply the go-first rule without
            // knowing slot numbers: "me" = our own portal, "them" = someone else's.
            const char* who = (missile._misource == MyPlayerId) ? "me" : "them";
            portals << static_cast<int>(missile.position.tile.x) << ","
                    << static_cast<int>(missile.position.tile.y) << "," << who;
            first = false;
        }
        if (!first)
            dsl << " TP=" << portals.str();
    }

    // Hazard layer: HZ=x,y,kind;... — active hostile missiles/AoE near us, so the
    // agent can "see the fire" and step off dangerous tiles. Sourced from the live
    // Missiles list, exactly like TP= above. Only missiles cast AT players
    // (TARGET_PLAYERS / TARGET_BOTH) count — that cleanly excludes our own and the
    // human's offensive spells (TARGET_MONSTERS), so we never flag her own Firebolt.
    // kind is the missile's damage element (fire/lght/acid/arc/phys) so Track D can
    // later scale per-element tolerance (fire-tolerance slider). v1 covers missile
    // hazards only; ground terrain (lava tiles, etc.) is a deferred v2. Emitted
    // unconditionally — NOT gated on dungeon-vs-town (the KS= bug-chain lesson).
    {
        std::ostringstream hazards;
        bool first = true;
        // A bit beyond light radius so incoming projectiles give reaction time.
        const int hazardRadius = (player->_pLightRad > 0 ? player->_pLightRad : 10) + 3;
        for (auto &missile : Missiles) {
            // Skip our own / the human's offensive missiles and benign ones.
            if (missile._micaster != TARGET_PLAYERS && missile._micaster != TARGET_BOTH)
                continue;
            if (missile._mitype == MissileID::TownPortal)
                continue;
            Point hp = missile.position.tile;
            int dx = std::abs(hp.x - playerPos.x);
            int dy = std::abs(hp.y - playerPos.y);
            if (static_cast<int>(std::sqrt(dx * dx + dy * dy)) > hazardRadius)
                continue;
            const char* kind;
            switch (GetMissileData(missile._mitype).damageType()) {
            case DamageType::Fire:      kind = "fire"; break;
            case DamageType::Lightning: kind = "lght"; break;
            case DamageType::Acid:      kind = "acid"; break;
            case DamageType::Magic:     kind = "arc";  break;
            default:                    kind = "phys"; break;
            }
            if (!first)
                hazards << ";";
            hazards << hp.x << "," << hp.y << "," << kind;
            first = false;
        }
        if (!first)
            dsl << " HZ=" << hazards.str();
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

            // Whether this item can actually be picked up and kept right now:
            // gold always; otherwise it must fit the inventory grid or the belt.
            // Engine-authoritative (no tetris guessing in Python) — the loot agent
            // uses it to avoid the pick-up-then-drop-back loop on a full pack.
            bool fits = item._itype == ItemType::Gold
                || CanFitItemInInventory(*player, item)
                || CanBePlacedOnBelt(*player, item);

            // Cast to int to avoid uint8_t being treated as char
            items << static_cast<int>(ActiveItems[i]) << "@"
                  << itemPos.x << "," << itemPos.y << ","
                  << value << "," << type_code << "," << qual_code
                  << "," << (fits ? 1 : 0);
        }
    }

    if (!first_item) {
        dsl << " L=" << items.str();
    }

    // Objects: OBJ=id@x,y,type;...
    // Types: ch=chest, tc=trapped_chest, dr=door, ba=barrel, sh=shrine, co=coffin
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
                // dr = closed (needs opening), do = already open. Without this the
                // agent can't tell, issues IN on an open door, and toggles it shut
                // (blocking the party). _oVar4: DOOR_CLOSED=0, DOOR_OPEN=1.
                type_code = (obj._oVar4 == /*DOOR_OPEN*/ 1) ? "do" : "dr";
            } else if (obj.IsBarrel()) {
                type_code = obj.isExplosive() ? "xb" : "ba";  // xb=explosive barrel
            } else if (obj.IsShrine()) {
                type_code = "sh";
            } else if (obj.IsSarcophagus()) {
                // co = coffin/sarcophagus. Operating it drops loot — but can also
                // wake a skeleton (engine: _oVar1 >= 8). The agent gates on HP.
                type_code = "co";
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

        // Format: type@slot#WxH  (footprint = grid cells the item occupies, from
        // the engine — so the agent reasons in grid AREA, not item count: a staff
        // is 1x3, gloves 1x1, a book 2x2.)
        Size fp = GetInventorySize(inv_item);
        inventory << type_code << "@" << i << "#" << fp.width << "x" << fp.height;
    }

    // Real grid occupancy: free vs used cells (of 40). This is what "full" means —
    // 15 big items can fill the grid. Always emitted (even with an empty pack).
    int freeCells = 0;
    for (int gi = 0; gi < InventoryGridCells; gi++)
        if (player->InvGrid[gi] == 0) freeCells++;

    if (!first_inv_item) {
        dsl << " INV=" << inventory.str();
        dsl << " INVC=" << inv_count;  // Total item count for quick reference
    }
    dsl << " INVFREE=" << freeCells;  // free grid cells of 40 (the real "fullness")

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

            // Only show store inventory if within 3 tiles. Must match the
            // agents' interaction range (e.g. griswold.py acts at dist <= 3):
            // if the store were visible only at <= 2 the agent would park at
            // dist 3 issuing a futile open command and never reach the sell.
            if (dist > 3) continue;

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

    // Known castable spells — ALWAYS emitted (town AND dungeon). This was the bug:
    // it lived inside the `if (DTYPE_TOWN)` block above, so underground the spell
    // menu vanished (nspells=0) and a caster couldn't see her own Firebolt. Self-
    // describing from engine metadata so the agent never hard-codes spell data:
    //   KS=id,name,lvl,mana,flags;...   (name spaces -> '_')
    //   flags: o=offensive(aimed), t=town-castable, $=affordable right now
    // RS=id is the readied (right-click) action; = memorized + class ability.
    {
        std::ostringstream spells;
        bool first_spell = true;
        uint64_t known = player->_pMemSpells | player->_pAblSpells;
        int curMana = player->_pMana >> 6;  // _pMana is fixed-point (>>6 = points)
        for (int s = 1; s < 64; s++) {
            SpellID sid = static_cast<SpellID>(s);
            // Test with the engine's own bitmask (1 << (id-1)) — NOT (known>>s),
            // which is off by one and skips Firebolt (id 1 -> bit 0) entirely.
            if (!(known & GetSpellBitmask(sid))) continue;
            const SpellData &sd = GetSpellData(sid);
            std::string name = sd.sNameText;
            for (char &c : name) if (c == ' ') c = '_';
            int mana = GetManaAmount(*player, sid) >> 6;  // GetManaAmount is fixed-point; >>6 = points
            std::string flags;
            if (sd.isTargeted()) flags += 'o';
            if (sd.isAllowedInTown()) flags += 't';
            if (mana <= curMana) flags += '$';
            if (flags.empty()) flags = "-";
            if (!first_spell) spells << ";";
            first_spell = false;
            spells << s << "," << name << "," << player->GetSpellLevel(sid)
                   << "," << mana << "," << flags;
        }
        if (!first_spell)
            dsl << " KS=" << spells.str();
        dsl << " RS=" << static_cast<int>(player->_pRSpell);
    }

    // Note: Could add E= (events) in the future for things like:
    // E=HIT:12,DROP:71,LEVEL_UP,etc.

    return dsl.str();
}

} // namespace devilution::gap
