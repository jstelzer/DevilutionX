#include "gap_state.h"
#include "gap_json.h"
#include "gap_core.h"
#ifdef ENABLE_GAP
#include "gap_chat.h"
#include "../actor/actor_store.h"
#include "../actor/player_actor.h"
#endif
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
#include <SDL.h>

namespace devilution::gap {

namespace {

// Get the controlled player for GAP operations
#ifdef ENABLE_GAP
PlayerActor* GetControlledPlayerActor() {
    auto& store = ActorStore::Instance();
    
    int controlled_slot = GapCore::Instance().GetControlledPlayer();
    PlayerActor* actor = store.GetPlayerActor(controlled_slot);
    if (actor && actor->IsValid()) {
        return actor;
    }
    
    // Fallback to main player if controlled player not available
    actor = store.GetPlayerActor(MyPlayerId);
    if (actor && actor->IsValid()) {
        return actor;
    }
    
    return nullptr;
}
#endif

// Legacy function for compatibility
Player* GetControlledPlayer() {
#ifdef ENABLE_GAP
    PlayerActor* actor = GetControlledPlayerActor();
    return actor ? actor->GetPlayer() : nullptr;
#else
    int controlled_slot = GapCore::Instance().GetControlledPlayer();
    if (controlled_slot >= 0 && controlled_slot < MAX_PLRS && Players[controlled_slot].plractive) {
        return &Players[controlled_slot];
    }
    // Fallback to MyPlayer if controlled player not available
    if (MyPlayerId < MAX_PLRS) {
        return &Players[MyPlayerId];
    }
    return nullptr;
#endif
}

// Stair piece ID arrays from trigs.cpp
const uint16_t TownDownList[] = { 715, 714, 718, 719, 720, 722, 723, 724, 725, 726, 119, 120, 123, 124, 125, 126 };
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
#ifdef ENABLE_GAP
    // Phase 3 Milestone C1: Use Actor interface for unified access
    PlayerActor* actor = GetControlledPlayerActor();
    if (actor == nullptr) {
        return "{}";
    }
    
    JsonBuilder state;
    state.BeginObject()
        .AddInt("hp", actor->GetHitPoints())
        .AddInt("hp_max", actor->GetMaxHitPoints())
        .AddInt("mana", actor->GetMana())
        .AddInt("mana_max", actor->GetMaxMana())
        .AddArray("pos", {actor->GetPosition().x, actor->GetPosition().y})
        .AddInt("level", actor->GetLevel())
        .AddBool("in_town", actor->IsInTown());
    
    // Access Player-specific data for belt (still needed for detailed info)
    Player* player = actor->GetPlayer();
#else
    // Legacy path when GAP disabled
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        return "{}";
    }
    
    JsonBuilder state;
    state.BeginObject()
        .AddInt("hp", player->_pHitPoints >> 6)
        .AddInt("hp_max", player->_pMaxHP >> 6)
        .AddInt("mana", player->_pMana >> 6)
        .AddInt("mana_max", player->_pMaxMana >> 6)
        .AddArray("pos", {player->position.tile.x, player->position.tile.y})
        .AddInt("level", static_cast<int>(currlevel))
        .AddBool("in_town", leveltype == DTYPE_TOWN);
#endif
    
    // Add belt information
    std::stringstream belt_json;
    belt_json << "[";
    for (int i = 0; i < MaxBeltItems; i++) {
        if (i > 0) belt_json << ",";
        
        const auto& belt_item = player->SpdList[i];
        if (!belt_item.isEmpty()) {
            std::string itemName = std::string(belt_item.getName());
            std::string itemType = "unknown";
            
            if (belt_item._itype == ItemType::Misc) {
                switch (belt_item._iMiscId) {
                    case IMISC_HEAL:
                    case IMISC_FULLHEAL:
                        itemType = "hp";
                        break;
                    case IMISC_MANA:
                    case IMISC_FULLMANA:
                        itemType = "mp";
                        break;
                    case IMISC_REJUV:
                    case IMISC_FULLREJUV:
                        itemType = "rejuv";
                        break;
                    default:
                        itemType = "misc";
                        break;
                }
            }
            
            belt_json << "{\"t\":\"" << itemType << "\",\"n\":" << belt_item._iCurs + 1 << "}";
        } else {
            belt_json << "null";
        }
    }
    belt_json << "]";
    
    state.AddRaw("belt", belt_json.str());
    
    // Add spell information (basic implementation)
    std::stringstream spells_json;
    spells_json << "{";
    // For now, just add placeholders - full spell integration needs more work
    spells_json << "\"slot1\":\"" << "Unknown" << "\",";
    spells_json << "\"slot2\":\"" << "Unknown" << "\"";
    spells_json << "}";
    
    state.AddRaw("spells", spells_json.str())
        .EndObject();
    
    return state.ToString();
}

std::string GapStateExtractor::ExtractNearbyEntities() {
    JsonBuilder result;
    result.BeginObject();
    
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        result.AddRaw("monsters", "[]")
              .AddRaw("items", "[]")
              .AddRaw("other_players", "[]")
              .AddRaw("vision", "{}")
              .EndObject();
        return result.ToString();
    }
    
    Point playerPos = player->position.tile;
    
    // Use player's actual light radius for vision
    int lightRadius = player->_pLightRad;
    if (lightRadius <= 0) lightRadius = 10; // Default fallback
    
    // IMPORTANT: For companions, we need to ensure they're on the same level as main player
    // and that monster data is available
    int controlled_slot = GapCore::Instance().GetControlledPlayer();
    if (controlled_slot != MyPlayerId && controlled_slot >= 0) {
        // Companion mode - ensure we're using proper game state
        std::cout << "GAP: Companion mode - checking level sync. Companion level=" 
                  << static_cast<int>(player->plrlevel) 
                  << " Main player level=" << static_cast<int>(Players[MyPlayerId].plrlevel) 
                  << " currlevel=" << static_cast<int>(currlevel) << std::endl;
    }
    
    // Reduced logging - only log position changes and player status
    static Point lastPlayerPos = {-1, -1};
    static int lastActiveCount = -1;
    
    if (playerPos.x != lastPlayerPos.x || playerPos.y != lastPlayerPos.y) {
        // Player moved - update last position (removed excessive logging)
        lastPlayerPos = playerPos;
    }
    
    // Log active players when count changes
    int activePlayerCount = 0;
    for (int i = 0; i < MAX_PLRS; i++) {
        if (Players[i].plractive) activePlayerCount++;
    }
    
    if (activePlayerCount != lastActiveCount) {
        std::cout << "GAP: Active players: " << activePlayerCount << " (";
        for (int i = 0; i < MAX_PLRS; i++) {
            if (Players[i].plractive) {
                std::cout << "slot" << i << ":" << Players[i]._pName;
                if (i == GapCore::Instance().GetControlledPlayer()) std::cout << "*";
                std::cout << " ";
            }
        }
        std::cout << ")" << std::endl;
        lastActiveCount = activePlayerCount;
    }
    
    std::stringstream monsters_json;
    monsters_json << "[";
    bool first_monster = true;
    
    // Debug logging for companion monster visibility
    static int lastMonsterCount = -1;
    static int lastDebugTime = 0;
    int currentTime = SDL_GetTicks();
    
    // Log every 2 seconds or when monster count changes
    if (currentTime - lastDebugTime > 2000 || static_cast<int>(ActiveMonsterCount) != lastMonsterCount) {
        std::cout << "GAP Debug: Controlled slot=" << controlled_slot 
                  << " Player HP=" << (player->_pHitPoints >> 6) << "/" << (player->_pMaxHP >> 6)
                  << " Pos=(" << playerPos.x << "," << playerPos.y << ")"
                  << " LightRadius=" << lightRadius 
                  << " ActiveMonsters=" << ActiveMonsterCount 
                  << " currlevel=" << static_cast<int>(currlevel) << std::endl;
        lastDebugTime = currentTime;
        lastMonsterCount = ActiveMonsterCount;
    }
    
    for (size_t i = 0; i < ActiveMonsterCount; i++) {
        const auto& monster = Monsters[ActiveMonsters[i]];
        Point monsterPos = monster.position.tile;
        
        int dx = std::abs(monsterPos.x - playerPos.x);
        int dy = std::abs(monsterPos.y - playerPos.y);
        
        // Use Euclidean distance for more natural visibility
        int distance = static_cast<int>(std::sqrt(dx * dx + dy * dy));
        
        // Debug: Log first 3 monsters for companion
        if (controlled_slot > 0 && i < 3) {
            std::cerr << "GAP: Monster[" << i << "] " << monster.name() 
                      << " at (" << monsterPos.x << "," << monsterPos.y << ") dist=" << distance 
                      << " (radius=" << lightRadius << ") -> " << (distance <= lightRadius ? "VISIBLE" : "OUT_OF_RANGE") << std::endl;
        }
        
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
    
    // Create compact walkability grid (7x7 instead of full light radius)
    // This gives immediate tactical awareness without overwhelming data
    int grid_radius = std::min(3, lightRadius); // Max 7x7 grid
    std::stringstream walkable_json;
    walkable_json << "[";
    bool first_row = true;
    
    for (int dy = -grid_radius; dy <= grid_radius; dy++) {
        if (!first_row) walkable_json << ",";
        first_row = false;
        
        walkable_json << "[";
        bool first_col = true;
        
        for (int dx = -grid_radius; dx <= grid_radius; dx++) {
            if (!first_col) walkable_json << ",";
            first_col = false;
            
            Point checkPos = {playerPos.x + dx, playerPos.y + dy};
            bool walkable = InDungeonBounds(checkPos) && IsTileNotSolid(checkPos);
            walkable_json << (walkable ? "1" : "0"); // Use 1/0 instead of true/false
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
    
    // Check for dungeon features within moderate radius for exploration
    // Use larger radius for stair detection so companions can follow leaders through level changes
    int exploration_radius = std::min(lightRadius + 5, 15);  // Larger radius for better stair detection
    for (int dy = -exploration_radius; dy <= exploration_radius; dy++) {
        for (int dx = -exploration_radius; dx <= exploration_radius; dx++) {
            Point checkPos = {playerPos.x + dx, playerPos.y + dy};
            
            if (InDungeonBounds(checkPos)) {
                uint16_t pieceId = dPiece[checkPos.x][checkPos.y];
                std::string detected_type = DetectStairType(pieceId, static_cast<int>(currlevel));
                
                // Debug: Log all non-zero piece IDs for stair detection debugging
                if (pieceId != 0 && ((checkPos.x == playerPos.x + dx && std::abs(checkPos.y - playerPos.y) <= 2) ||
                    (checkPos.y == playerPos.y + dy && std::abs(checkPos.x - playerPos.x) <= 2))) {
                    std::cout << "GAP Debug: Tile (" << checkPos.x << "," << checkPos.y << ") has pieceId=" << pieceId;
                    if (!detected_type.empty()) {
                        std::cout << " -> " << detected_type;
                    }
                    std::cout << std::endl;
                }
                
                if (!detected_type.empty()) {
                    stairs_visible = true;
                    stairs_pos = checkPos;
                    stairs_type = detected_type;
                    std::cout << "GAP Debug: STAIRS FOUND! Type=" << detected_type << " at (" << checkPos.x << "," << checkPos.y << ")" << std::endl;
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
    // Add limited frontier detection for systematic exploration  
    std::stringstream frontiers_json;
    frontiers_json << "[";
    bool first_frontier = true;
    int frontier_count = 0;
    const int max_frontiers = 10; // Limit to prevent JSON bloat
    
    // Simple frontier detection within smaller radius
    int frontier_radius = std::min(lightRadius, 6); // Limit search area
    for (int dy = -frontier_radius; dy <= frontier_radius; dy++) {
        for (int dx = -frontier_radius; dx <= frontier_radius; dx++) {
            if (frontier_count >= max_frontiers) break; // Stop when limit reached
            
            Point checkPos = {playerPos.x + dx, playerPos.y + dy};
            
            if (InDungeonBounds(checkPos) && IsTileNotSolid(checkPos)) {
                // Check if this tile is adjacent to unexplored areas
                bool is_frontier = false;
                for (int ndy = -1; ndy <= 1 && !is_frontier; ndy++) {
                    for (int ndx = -1; ndx <= 1; ndx++) {
                        Point neighbor = {checkPos.x + ndx, checkPos.y + ndy};
                        if (InDungeonBounds(neighbor)) {
                            // Simple heuristic: if tile is walkable but at edge of light radius
                            int dist_from_player = std::max(std::abs(neighbor.x - playerPos.x), 
                                                           std::abs(neighbor.y - playerPos.y));
                            if (dist_from_player >= lightRadius - 1) {
                                is_frontier = true;
                                break;
                            }
                        }
                    }
                }
                
                if (is_frontier) {
                    if (!first_frontier) frontiers_json << ",";
                    first_frontier = false;
                    frontiers_json << "[" << checkPos.x << "," << checkPos.y << "]";
                    frontier_count++;
                }
            }
        }
        if (frontier_count >= max_frontiers) break; // Stop when limit reached
    }
    frontiers_json << "]";
    
    exploration_json << ",\"objects\":" << objects_json.str();
    exploration_json << ",\"frontiers\":" << frontiers_json.str();
    exploration_json << "}";
    
    visionData.AddRaw("exploration", exploration_json.str())
        .EndObject();
    
    // Extract other players information
    std::ostringstream other_players_json;
    other_players_json << "[";
    bool first_other_player = true;
    
    // Reuse controlled_slot from earlier declaration
    
    for (int i = 0; i < MAX_PLRS; i++) {
        if (i == controlled_slot || !Players[i].plractive) {
            continue; // Skip self and inactive players
        }
        
        const Player& other_player = Players[i];
        
        // Safety check: ensure player name is valid  
        if (strlen(other_player._pName) == 0) {
            continue; // Skip players with empty names
        }
        Point otherPos = other_player.position.tile;
        
        // Calculate distance from controlled player
        int distance = std::abs(otherPos.x - playerPos.x) + std::abs(otherPos.y - playerPos.y);
        
        // Only include players within reasonable range (same as monster range)
        if (distance > lightRadius + 5) {
            continue;
        }
        
        if (!first_other_player) {
            other_players_json << ",";
        }
        first_other_player = false;
        
        // Compact format: [id, name, x, y, distance, hp%, dlevel, is_leader]
        int hp_percent = (other_player._pMaxHP > 0) ? (other_player._pHitPoints * 100 / other_player._pMaxHP) : 0;
        bool is_leader = (i == MyPlayerId);  // MyPlayerId is always the human player (leader)
        
        // Escape quotes in player name to prevent JSON corruption
        std::string safe_name = other_player._pName;
        size_t pos = 0;
        while ((pos = safe_name.find("\"", pos)) != std::string::npos) {
            safe_name.replace(pos, 1, "\\\"");
            pos += 2;
        }
        
        // Ensure dungeon level is a valid integer (not null byte)
        int dungeon_level = static_cast<int>(other_player.plrlevel);
        
        other_players_json << "["
            << i << ","
            << "\"" << safe_name << "\","
            << otherPos.x << "," << otherPos.y << ","
            << distance << ","
            << hp_percent << ","
            << dungeon_level << ","
            << (is_leader ? "true" : "false")
            << "]";
    }
    other_players_json << "]";

    result.AddRaw("monsters", monsters_json.str())
          .AddRaw("items", items_json.str())
          .AddRaw("other_players", other_players_json.str())
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