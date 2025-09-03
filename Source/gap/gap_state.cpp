#include "gap_state.h"
#include "gap_json.h"
#include "../player.h"
#include "../monster.h"
#include "../items.h"
#include "../diablo.h"
#include "../levels/town.h"
#include "../levels/tile_properties.hpp"
#include "../levels/gendung.h"
#include "../stores.h"
#include "../nthread.h"
#include "../objects.h"
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <cmath>

namespace devilution::gap {

namespace {
// Stair piece ID arrays from trigs.cpp
const uint16_t TownDownList[] = { 715, 714, 718, 719, 720, 722, 723, 724, 725, 726 };
const uint16_t TownWarp1List[] = { 1170, 1171, 1172, 1173, 1174, 1175, 1176, 1177, 1178, 1180, 1182, 1184 };
const uint16_t TownCryptList[] = { 1330, 1331, 1332, 1333, 1334, 1335, 1336, 1337 };
const uint16_t TownHiveList[] = { 1306, 1307, 1308, 1309 };
const uint16_t L1UpList[] = { 126, 128, 129, 130, 131, 132, 134, 136, 137, 138, 139 };
const uint16_t L1DownList[] = { 105, 106, 107, 108, 109, 111, 113, 114, 117 };
const uint16_t L2UpList[] = { 265, 266 };
const uint16_t L2DownList[] = { 268, 269, 270, 271 };
const uint16_t L2TWarpUpList[] = { 557, 558 };
const uint16_t L3UpList[] = { 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182 };
const uint16_t L3DownList[] = { 161, 162, 163, 164, 165, 166, 167, 168 };
const uint16_t L3TWarpUpList[] = { 181, 547, 548, 549, 550, 551, 552, 553, 554, 555, 556, 557, 558, 559 };
const uint16_t L4UpList[] = { 81, 82, 89 };
const uint16_t L4DownList[] = { 119, 129, 130, 131, 132 };
const uint16_t L4TWarpUpList[] = { 420, 421, 428 };

std::string DetectStairType(uint16_t pieceId, int currentLevel) {
    // Town checks
    if (currentLevel == 0) {  // Town
        for (uint16_t id : TownDownList) if (id == pieceId) return "down_cathedral";
        for (uint16_t id : TownWarp1List) if (id == pieceId) return "down_catacombs"; 
        for (uint16_t id : TownCryptList) if (id == pieceId) return "down_crypt";
        for (uint16_t id : TownHiveList) if (id == pieceId) return "down_hive";
    }
    // Cathedral checks
    else if (currentLevel >= 1 && currentLevel <= 4) {
        for (uint16_t id : L1UpList) if (id == pieceId) return "up_town";
        for (uint16_t id : L1DownList) if (id == pieceId) return "down_next";
    }
    // Catacombs checks  
    else if (currentLevel >= 5 && currentLevel <= 8) {
        for (uint16_t id : L2UpList) if (id == pieceId) return "up_prev";
        for (uint16_t id : L2DownList) if (id == pieceId) return "down_next";
        for (uint16_t id : L2TWarpUpList) if (id == pieceId) return "up_town";
    }
    // Caves checks
    else if (currentLevel >= 9 && currentLevel <= 12) {
        for (uint16_t id : L3UpList) if (id == pieceId) return "up_prev";
        for (uint16_t id : L3DownList) if (id == pieceId) return "down_next";
        for (uint16_t id : L3TWarpUpList) if (id == pieceId) return "up_town";
    }
    // Hell checks
    else if (currentLevel >= 13 && currentLevel <= 16) {
        for (uint16_t id : L4UpList) if (id == pieceId) return "up_prev";
        for (uint16_t id : L4DownList) if (id == pieceId) return "down_diablo";
        for (uint16_t id : L4TWarpUpList) if (id == pieceId) return "up_town";
    }
    
    return ""; // No stairs detected
}
} // anonymous namespace

std::string GapStateExtractor::ExtractState(uint32_t tick, uint32_t tick_rate) {
    auto now = std::chrono::system_clock::now();
    auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count();
    
    JsonBuilder state;
    state.BeginObject()
        .AddString("type", "state")
        .AddUInt("tick", tick)
        .AddUInt("tick_rate", tick_rate)
        .AddUInt("timestamp", static_cast<uint32_t>(timestamp));
    
    JsonBuilder data;
    data.BeginObject()
        .AddRaw("player", ExtractPlayerState())
        .AddRaw("nearby", ExtractNearbyEntities())
        .AddRaw("ui_state", ExtractUIState())
        .EndObject();
    
    state.AddRaw("data", data.ToString())
        .EndObject();
    
    return state.ToString();
}

std::string GapStateExtractor::ExtractPlayerState() {
    if (MyPlayerId >= MAX_PLRS) {
        return "{}";
    }
    
    const auto& player = Players[MyPlayerId];
    
    JsonBuilder state;
    state.BeginObject()
        .AddInt("hp", player._pHitPoints >> 6)
        .AddInt("hp_max", player._pMaxHP >> 6)
        .AddInt("mana", player._pMana >> 6)
        .AddInt("mana_max", player._pMaxMana >> 6)
        .AddArray("pos", {player.position.tile.x, player.position.tile.y})
        .AddInt("level", static_cast<int>(currlevel))
        .AddBool("in_town", leveltype == DTYPE_TOWN)
        .EndObject();
    
    return state.ToString();
}

std::string GapStateExtractor::ExtractNearbyEntities() {
    JsonBuilder result;
    result.BeginObject();
    
    if (MyPlayerId >= MAX_PLRS) {
        result.AddRaw("monsters", "[]")
              .AddRaw("items", "[]")
              .AddRaw("other_players", "[]")
              .AddRaw("vision", "{}")
              .EndObject();
        return result.ToString();
    }
    
    const auto& player = Players[MyPlayerId];
    Point playerPos = player.position.tile;
    
    // Use player's actual light radius for vision
    int lightRadius = player._pLightRad;
    if (lightRadius <= 0) lightRadius = 10; // Default fallback
    
    // Debug: Log player position and status
    std::cerr << "GAP: Player at (" << playerPos.x << "," << playerPos.y << ") light_radius=" << lightRadius;
    std::cerr << " level=" << static_cast<int>(currlevel) << " in_town=" << (leveltype == DTYPE_TOWN ? "true" : "false") << std::endl;
    
    std::stringstream monsters_json;
    monsters_json << "[";
    bool first_monster = true;
    
    // Debug: Log monster scan
    std::cerr << "GAP: Scanning " << ActiveMonsterCount << " monsters within radius " << lightRadius << std::endl;
    
    for (size_t i = 0; i < ActiveMonsterCount; i++) {
        const auto& monster = Monsters[ActiveMonsters[i]];
        Point monsterPos = monster.position.tile;
        
        int dx = std::abs(monsterPos.x - playerPos.x);
        int dy = std::abs(monsterPos.y - playerPos.y);
        
        // Use Euclidean distance for more natural visibility
        int distance = static_cast<int>(std::sqrt(dx * dx + dy * dy));
        
        // Debug: Log each monster check (commented out to reduce spam)
        // std::cerr << "GAP: Monster " << i << " at (" << monsterPos.x << "," << monsterPos.y << ") euclidean_distance=" << distance << " vs radius " << lightRadius;
        
        if (distance <= lightRadius) {
            // std::cerr << " -> INCLUDED" << std::endl;
            if (!first_monster) monsters_json << ",";
            first_monster = false;
            
            // Use the same distance calculation for consistency
            
            // Get monster name, truncate if too long
            std::string monsterName(monster.name());
            if (monsterName.length() > 20) {
                monsterName = monsterName.substr(0, 20);
            }
            
            JsonBuilder monsterData;
            monsterData.BeginObject()
                .AddInt("id", static_cast<int>(ActiveMonsters[i]))
                .AddString("name", monsterName)
                .AddArray("pos", {monsterPos.x, monsterPos.y})
                .AddInt("distance", distance)
                .AddInt("hp", monster.hitPoints)
                .AddInt("hp_max", monster.maxHitPoints)
                .AddInt("hp_percent", monster.hitPoints > 0 ? 
                    (monster.hitPoints * 100 / monster.maxHitPoints) : 0)
                .AddInt("armor", monster.armorClass)
                .AddBool("is_minion", monster.isPlayerMinion())
                .AddBool("is_alive", monster.hitPoints > 0)
                .EndObject();
            monsters_json << monsterData.ToString();
        } else {
            // std::cerr << " -> FILTERED OUT" << std::endl;
        }
    }
    monsters_json << "]";
    
    std::stringstream items_json;
    items_json << "[";
    bool first_item = true;
    
    for (uint8_t i = 0; i < ActiveItemCount; i++) {
        const auto& item = Items[ActiveItems[i]];
        Point itemPos = item.position;
        
        int dx = std::abs(itemPos.x - playerPos.x);
        int dy = std::abs(itemPos.y - playerPos.y);
        
        if (dx <= lightRadius && dy <= lightRadius) {
            if (!first_item) items_json << ",";
            first_item = false;
            
            // Get item name and type for LLM context
            std::string itemName = std::string(item.getName());
            if (itemName.length() > 25) {
                itemName = itemName.substr(0, 25);
            }
            
            // Basic item categorization for LLM decision making  
            std::string itemType = "unknown";
            if (item.isGold()) {
                itemType = "gold";
            } else if (item.isScroll()) {
                itemType = "scroll";
            } else if (itemName.find("Potion") != std::string::npos || itemName.find("Elixir") != std::string::npos) {
                itemType = "potion";
            } else if (item.isWeapon()) {
                itemType = "weapon";
            } else if (item.isArmor()) {
                itemType = "armor";
            } else if (itemName.find("Ring") != std::string::npos) {
                itemType = "ring";
            } else if (itemName.find("Amulet") != std::string::npos) {
                itemType = "amulet";
            }
            
            JsonBuilder itemData;
            itemData.BeginObject()
                .AddInt("id", static_cast<int>(ActiveItems[i]))
                .AddArray("pos", {itemPos.x, itemPos.y})
                .AddString("name", itemName)
                .AddString("type", itemType);
            
            // Add value for gold items
            if (item.isGold()) {
                itemData.AddInt("value", item._ivalue);
            }
            
            itemData.EndObject();
            items_json << itemData.ToString();
        }
    }
    items_json << "]";
    
    // Add vision/walkability data for LLM spatial awareness
    JsonBuilder visionData;
    visionData.BeginObject()
        .AddInt("light_radius", lightRadius)
        .AddArray("player_pos", {playerPos.x, playerPos.y});
    
    // Create walkability grid within light radius
    std::stringstream walkable_json;
    walkable_json << "[";
    bool first_row = true;
    
    for (int dy = -lightRadius; dy <= lightRadius; dy++) {
        if (!first_row) walkable_json << ",";
        first_row = false;
        
        walkable_json << "[";
        bool first_col = true;
        
        for (int dx = -lightRadius; dx <= lightRadius; dx++) {
            if (!first_col) walkable_json << ",";
            first_col = false;
            
            Point checkPos = {playerPos.x + dx, playerPos.y + dy};
            bool walkable = InDungeonBounds(checkPos) && IsTileNotSolid(checkPos);
            walkable_json << (walkable ? "true" : "false");
        }
        
        walkable_json << "]";
    }
    walkable_json << "]";
    
    visionData.AddRaw("walkable_grid", walkable_json.str());
    
    // Add broader exploration data for map completion
    std::stringstream exploration_json;
    exploration_json << "{";
    
    // Detect stairs/portals in visible area for level progression
    bool stairs_visible = false;
    Point stairs_pos = {0, 0};
    std::string stairs_type = "";
    
    // Check for dungeon features within larger radius for exploration
    int exploration_radius = lightRadius * 2;  // Larger area for exploration
    for (int dy = -exploration_radius; dy <= exploration_radius; dy++) {
        for (int dx = -exploration_radius; dx <= exploration_radius; dx++) {
            Point checkPos = {playerPos.x + dx, playerPos.y + dy};
            
            if (InDungeonBounds(checkPos)) {
                uint16_t pieceId = dPiece[checkPos.x][checkPos.y];
                std::string detected_type = DetectStairType(pieceId, static_cast<int>(currlevel));
                
                if (!detected_type.empty()) {
                    stairs_visible = true;
                    stairs_pos = checkPos;
                    stairs_type = detected_type;
                    break; // Found stairs, exit search
                }
            }
        }
        if (stairs_visible) break;
    }
    
    // Find interactive objects (chests, barrels, etc.) within exploration radius
    std::stringstream objects_json;
    objects_json << "[";
    bool first_object = true;
    
    for (int i = 0; i < ActiveObjectCount; i++) {
        const auto& obj = Objects[ActiveObjects[i]];
        Point objPos = obj.position;
        
        int dx = std::abs(objPos.x - playerPos.x);
        int dy = std::abs(objPos.y - playerPos.y);
        int distance = static_cast<int>(std::sqrt(dx * dx + dy * dy));
        
        if (distance <= exploration_radius) {
            std::string objType = "";
            
            if (obj.IsChest()) {
                objType = obj.IsTrappedChest() ? "trapped_chest" : "chest";
            } else if (obj.IsBarrel()) {
                objType = obj.isExplosive() ? "explosive_barrel" : "barrel";
            } else if (obj.IsShrine()) {
                objType = "shrine";
            } else if (obj.isDoor()) {
                objType = "door";
            }
            
            if (!objType.empty()) {
                if (!first_object) objects_json << ",";
                first_object = false;
                
                JsonBuilder objData;
                objData.BeginObject()
                    .AddInt("id", static_cast<int>(ActiveObjects[i]))
                    .AddString("type", objType)
                    .AddArray("pos", {objPos.x, objPos.y})
                    .AddInt("distance", distance)
                    .EndObject();
                objects_json << objData.ToString();
            }
        }
    }
    objects_json << "]";
    
    exploration_json << "\"current_level\":" << static_cast<int>(currlevel) << ",";
    exploration_json << "\"exploration_radius\":" << exploration_radius << ",";
    exploration_json << "\"stairs_visible\":" << (stairs_visible ? "true" : "false");
    if (stairs_visible) {
        exploration_json << ",\"stairs_pos\":[" << stairs_pos.x << "," << stairs_pos.y << "],";
        exploration_json << "\"stairs_type\":\"" << stairs_type << "\"";
    }
    exploration_json << ",\"objects\":" << objects_json.str();
    exploration_json << "}";
    
    visionData.AddRaw("exploration", exploration_json.str())
        .EndObject();
    
    result.AddRaw("monsters", monsters_json.str())
          .AddRaw("items", items_json.str())
          .AddRaw("other_players", "[]")
          .AddRaw("vision", visionData.ToString())
          .EndObject();
    
    return result.ToString();
}

std::string GapStateExtractor::ExtractUIState() {
    JsonBuilder state;
    state.BeginObject()
        .AddBool("in_menu", false)
        .AddBool("in_store", IsPlayerInStore())
        .AddBool("can_act", !gbIsMultiplayer || !nthread_has_500ms_passed(nullptr))
        .EndObject();
    
    return state.ToString();
}

} // namespace devilution::gap