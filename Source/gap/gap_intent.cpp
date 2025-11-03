#include "gap_intent.h"
#include "gap_json.h"
#include "gap_core.h"
#include "gap_network.h"
#include "gap_stores.h"
#ifdef ENABLE_GAP
#include "gap_chat.h"
#include "../seat/seat.h"
#include "../seat/companion_seat.h"
#endif
#include "../player.h"
#include "../monster.h"
#include "../cursor.h"
#include "../control.h"
#include "../engine/point.hpp"
#include "../levels/gendung.h"
#include "../nthread.h"
#include "../msg.h"
#include "../items.h"
#include "../objects.h"
#include "../spells.h"
#include "../inv.h"
#include "../controls/plrctrls.h"
#include "../engine/backbuffer_state.hpp"
#include <iostream>
#include <sstream>

namespace devilution::gap {

namespace {
// Get the controlled player for GAP operations
Player* GetControlledPlayer() {
    int controlled_slot = GapCore::Instance().GetControlledPlayer();
    std::cerr << "GAP: GetControlledPlayer - controlled_slot=" << controlled_slot 
              << " MyPlayerId=" << MyPlayerId << std::endl;
    
    if (controlled_slot >= 0 && controlled_slot < MAX_PLRS) {
        bool is_active = Players[controlled_slot].plractive;
        std::cerr << "GAP: Checking slot " << controlled_slot 
                  << " - plractive=" << is_active;
        if (is_active) {
            std::cerr << " name=" << Players[controlled_slot]._pName;
        }
        std::cerr << std::endl;
        
        if (is_active) {
            return &Players[controlled_slot];
        }
    }
    
    // Fallback to MyPlayer if controlled player not available
    std::cerr << "GAP: Falling back to MyPlayerId=" << MyPlayerId << std::endl;
    if (MyPlayerId < MAX_PLRS) {
        return &Players[MyPlayerId];
    }
    return nullptr;
}

// Get the controlled player ID for GAP operations  
int GetControlledPlayerId() {
    int controlled_slot = GapCore::Instance().GetControlledPlayer();
    if (controlled_slot >= 0 && controlled_slot < MAX_PLRS && Players[controlled_slot].plractive) {
        return controlled_slot;
    }
    // Fallback to MyPlayerId
    return MyPlayerId;
}
} // namespace

void GapIntentProcessor::QueueIntent(const JsonParser& intent_msg) {
    if (intent_queue_.size() >= 3) {
        std::cerr << "GAP: Intent queue full, dropping intent" << std::endl;
        return;
    }
    
    Intent intent;
    
    // Check for compact format first ({"m":[x,y]}, {"a":id}, {"p":id}, etc.)
    if (intent_msg.HasKey("m")) {
        // Compact move: {"m":[x,y]}
        intent.action = "move";
        std::string move_str = intent_msg.GetObjectString("m");
        // Parse array [x,y] from string like "[50,55]"
        if (move_str.size() >= 5 && move_str[0] == '[' && move_str.back() == ']') {
            std::string coords = move_str.substr(1, move_str.size() - 2); // Remove [ ]
            size_t comma_pos = coords.find(',');
            if (comma_pos != std::string::npos) {
                intent.param_x = std::stoi(coords.substr(0, comma_pos));
                intent.param_y = std::stoi(coords.substr(comma_pos + 1));
            }
        }
    } else if (intent_msg.HasKey("a")) {
        // Compact attack: {"a":monster_id} or {"a":[x,y]}
        intent.action = "attack";
        std::string attack_str = intent_msg.GetObjectString("a");
        if (attack_str.size() > 0 && attack_str[0] == '[') {
            // Position attack: {"a":[x,y]}
            if (attack_str.size() >= 5 && attack_str.back() == ']') {
                std::string coords = attack_str.substr(1, attack_str.size() - 2); // Remove [ ]
                size_t comma_pos = coords.find(',');
                if (comma_pos != std::string::npos) {
                    intent.param_x = std::stoi(coords.substr(0, comma_pos));
                    intent.param_y = std::stoi(coords.substr(comma_pos + 1));
                }
            }
        } else {
            // Monster attack: {"a":42}
            intent.param_x = intent_msg.GetInt("a");
            intent.param_y = -1;
        }
    } else if (intent_msg.HasKey("p")) {
        // Compact pickup: {"p":item_id}
        intent.action = "pickup";
        intent.param_id = intent_msg.GetInt("p");
    } else if (intent_msg.HasKey("h")) {
        // Compact use potion: {"h":slot}
        intent.action = "use_potion";
        intent.param_slot = intent_msg.GetInt("h");
        intent.param_kind = "hp"; // Default to health potion
    } else if (intent_msg.HasKey("c")) {
        // Compact chat: {"c":"message"}
        intent.action = "chat";
        intent.param_kind = intent_msg.GetString("c");
    } else {
        // Standard format: {"type":"intent","action":"move","params":{"x":50,"y":55}}
        intent.action = intent_msg.GetString("action");
        
        std::string params_str = intent_msg.GetObjectString("params");
        JsonParser params(params_str);
        intent.param_x = params.GetInt("x");
        intent.param_y = params.GetInt("y");
        intent.param_id = params.GetInt("id");
        intent.param_slot = params.GetInt("slot");
        intent.param_kind = params.GetString("kind");
    }
    
    intent.target_tick = intent_msg.GetInt("target_tick");

    intent_queue_.push(intent);
}

void GapIntentProcessor::QueueDSLIntent(const std::string& dsl_line) {
    if (intent_queue_.size() >= 3) {
        std::cerr << "GAP: Intent queue full, dropping DSL intent" << std::endl;
        return;
    }

    // Parse DSL command: "MV x y", "AT id", "PK id", etc.
    std::istringstream iss(dsl_line);
    std::string cmd;
    iss >> cmd;

    if (cmd.empty()) {
        return;  // Empty line, ignore
    }

    Intent intent;
    intent.param_x = 0;
    intent.param_y = 0;
    intent.param_id = 0;
    intent.param_slot = -1;
    intent.param_inv_slot = -1;
    intent.target_tick = 0;

    if (cmd == "MV") {
        // MV x y
        intent.action = "move";
        iss >> intent.param_x >> intent.param_y;

    } else if (cmd == "AT") {
        // AT id OR AT x y
        intent.action = "attack";

        // Try to read first parameter
        if (iss >> intent.param_x) {
            // Check if there's a second parameter (position attack)
            if (iss >> intent.param_y) {
                // Two parameters: AT x y (position-based attack for ranged)
                intent.param_id = 0;  // No monster ID
            } else {
                // One parameter: AT id (monster ID attack)
                intent.param_id = intent.param_x;
                intent.param_x = 0;
                intent.param_y = -1;  // Marker for "convert ID to position"
            }
        }

    } else if (cmd == "PK") {
        // PK id
        intent.action = "pickup";
        iss >> intent.param_id;

    } else if (cmd == "IN") {
        // IN id
        intent.action = "interact";
        iss >> intent.param_id;

    } else if (cmd == "CS") {
        // CS slot - Cast scroll from belt slot (0-7)
        // Example: CS 2  (use scroll in belt slot 2)
        intent.action = "cast";
        iss >> intent.param_slot;

    } else if (cmd == "US") {
        // US slot
        intent.action = "use_potion";
        iss >> intent.param_slot;
        intent.param_kind = "hp";  // Default to health potion

    } else if (cmd == "SAY") {
        // SAY text...
        intent.action = "chat";
        // Get rest of line as chat message
        std::getline(iss, intent.param_kind);
        // Trim leading space
        if (!intent.param_kind.empty() && intent.param_kind[0] == ' ') {
            intent.param_kind = intent.param_kind.substr(1);
        }

    } else if (cmd == "BUY") {
        // BUY npc_code item_index
        // Example: BUY hl 5  (buy item #5 from healer)
        std::string npc_code;
        iss >> npc_code >> intent.param_id;
        intent.action = "buy";
        intent.param_kind = npc_code;  // "sm", "hl", "wt", "pg"

    } else if (cmd == "SELL") {
        // SELL inv_slot
        // Example: SELL 7  (sell inventory slot 7)
        intent.action = "sell";
        iss >> intent.param_slot;

    } else if (cmd == "REP") {
        // REP inv_slot
        // Example: REP 3  (repair inventory slot 3)
        intent.action = "repair";
        iss >> intent.param_slot;

    } else if (cmd == "ID") {
        // ID inv_slot
        // Example: ID 2  (identify inventory slot 2)
        intent.action = "identify";
        iss >> intent.param_slot;

    } else if (cmd == "ADDSTAT") {
        // ADDSTAT stat_name
        // Example: ADDSTAT STR, ADDSTAT DEX, ADDSTAT MAG, ADDSTAT VIT
        std::string stat_name;
        iss >> stat_name;
        intent.action = "addstat";
        intent.param_kind = stat_name;  // "STR", "DEX", "MAG", "VIT"

    } else if (cmd == "BELT") {
        // BELT inv_slot belt_slot
        // Example: BELT 12 3  (move item from inventory slot 12 to belt slot 3)
        intent.action = "belt_refill";
        iss >> intent.param_inv_slot >> intent.param_slot;

    } else if (cmd == "DROP") {
        // DROP inv_slot OR DROP GOLD amount
        // Example: DROP 5  (drop item from inventory slot 5)
        // Example: DROP GOLD 1000  (drop 1000 gold)
        std::string param1;
        iss >> param1;
        if (param1 == "GOLD") {
            intent.action = "drop_gold";
            iss >> intent.param_x;  // Use param_x to store gold amount
        } else {
            intent.action = "drop_item";
            intent.param_inv_slot = std::stoi(param1);
        }

    } else {
        std::cerr << "GAP DSL: Unknown command: " << cmd << std::endl;
        return;
    }

    intent_queue_.push(intent);
    std::cout << "GAP DSL: Queued " << intent.action << " command" << std::endl;
}

void GapIntentProcessor::ProcessPendingIntents(uint32_t current_tick) {
    while (!intent_queue_.empty()) {
        const Intent& intent = intent_queue_.front();
        
        if (intent.target_tick > 0 && intent.target_tick > current_tick) {
            break;
        }
        
        if (ExecuteIntent(intent)) {
            std::cout << "GAP: Executed intent: " << intent.action << std::endl;
        } else {
            std::cerr << "GAP: Failed to execute intent: " << intent.action << std::endl;
        }
        
        intent_queue_.pop();
    }
}

bool GapIntentProcessor::ExecuteIntent(const Intent& intent) {
    if (intent.action == "move") {
        return ExecuteMove(intent.param_x, intent.param_y);
    } else if (intent.action == "attack") {
        // Check if we have a monster ID (DSL format: AT id) or position (JSON format)
        std::cerr << "GAP: ExecuteIntent attack - param_id=" << intent.param_id
                  << " param_x=" << intent.param_x << " param_y=" << intent.param_y << std::endl;
        if (intent.param_id > 0) {
            // Monster ID attack - pass as (monster_id, -1)
            std::cerr << "GAP: Using monster ID attack path" << std::endl;
            return ExecuteAttack(intent.param_id, -1);
        } else {
            // Position-based attack - pass as (x, y)
            std::cerr << "GAP: Using position-based attack path" << std::endl;
            return ExecuteAttack(intent.param_x, intent.param_y);
        }
    } else if (intent.action == "cast") {
        return ExecuteCast(intent.param_slot, intent.param_x, intent.param_y);
    } else if (intent.action == "use_potion") {
        return ExecuteUsePotion(intent.param_kind, intent.param_slot);
    } else if (intent.action == "pickup") {
        return ExecutePickup(intent.param_id);
    } else if (intent.action == "interact") {
        return ExecuteInteract(intent.param_id);
    } else if (intent.action == "path") {
        return ExecutePath(intent.param_x, intent.param_y);
    } else if (intent.action == "explore") {
        return ExecuteExplore();
    } else if (intent.action == "chat") {
        return ExecuteChat(intent.param_kind);
    } else if (intent.action == "buy") {
        return ExecuteBuy(intent.param_kind, intent.param_id);
    } else if (intent.action == "sell") {
        return ExecuteSell(intent.param_slot);
    } else if (intent.action == "repair") {
        return ExecuteRepair(intent.param_slot);
    } else if (intent.action == "identify") {
        return ExecuteIdentify(intent.param_slot);
    } else if (intent.action == "addstat") {
        return ExecuteAddStat(intent.param_kind);
    } else if (intent.action == "belt_refill") {
        return ExecuteBeltRefill(intent.param_inv_slot, intent.param_slot);
    } else if (intent.action == "drop_item") {
        return ExecuteDropItem(intent.param_inv_slot);
    } else if (intent.action == "drop_gold") {
        return ExecuteDropGold(intent.param_x);
    }

    std::cerr << "GAP: Unknown intent action: " << intent.action << std::endl;
    return false;
}

bool GapIntentProcessor::ExecuteMove(int x, int y) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP: ExecuteMove failed - GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }
    
    int controlled_id = GetControlledPlayerId();
    std::cerr << "GAP: ExecuteMove - Controlling player " << controlled_id 
              << " (name: " << player->_pName << ")" 
              << " at pos (" << player->position.tile.x << "," << player->position.tile.y << ")"
              << " to target (" << x << "," << y << ")" << std::endl;
    
    if (player->_pmode != PM_STAND) {
        std::cerr << "GAP: ExecuteMove failed - player mode is " << player->_pmode << " (not PM_STAND)" << std::endl;
        return false;
    }
    
    Point target(x, y);
    
    if (!InDungeonBounds(target)) {
        std::cerr << "GAP: ExecuteMove failed - target (" << x << "," << y << ") out of dungeon bounds" << std::endl;
        return false;
    }
    
    if (player->position.tile == target) {
        std::cerr << "GAP: ExecuteMove failed - already at target position" << std::endl;
        return false; // Already at target
    }
    
    // Use the game's pathfinding system like the normal controls do
    MakePlrPath(*player, target, true);
    player->destAction = ACTION_WALK;
    
    // Handle both single-player and multiplayer modes
    // In single-player mode with companion, we need direct execution
    // In multiplayer, use network isolation for correct routing
    if (controlled_id != MyPlayerId) {
        // Controlling a companion - use direct execution
        std::cerr << "GAP: Using direct execution for companion " << controlled_id << std::endl;
        return ExecuteDirectMove(controlled_id, target);
    } else if (gbIsMultiplayer) {
        // Controlling main player in multiplayer
        std::cerr << "GAP: Sending network command CMD_WALKXY for player " << controlled_id << std::endl;
        NetSendCmdLocForPlayer(controlled_id, true, CMD_WALKXY, target);
    }
    
    std::cerr << "GAP: ExecuteMove succeeded - path set for player " << controlled_id << std::endl;
    return true;
}

bool GapIntentProcessor::ExecuteAttack(int x, int y) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        return false;
    }

    // Check if player is already attacking - prevent spam
    if (player->_pmode == PM_ATTACK || player->_pmode == PM_RATTACK) {
        // Already attacking, don't spam attacks
        return false;
    }

    // Allow attacking while walking or standing
    if (player->_pmode != PM_STAND &&
        player->_pmode != PM_WALK_NORTHWARDS &&
        player->_pmode != PM_WALK_SOUTHWARDS &&
        player->_pmode != PM_WALK_SIDEWAYS) {
        std::cerr << "GAP: ExecuteAttack - Player not in attackable mode (mode=" << player->_pmode << ")" << std::endl;
        return false;
    }
    
    // Check if we have a monster ID passed as x (when y is -1)
    // This allows attacking specific monsters by ID
    if (y == -1) {
        int monsterId = x;
        if (monsterId >= 0 && static_cast<size_t>(monsterId) < MaxMonsters) {
            const auto& monster = Monsters[monsterId];
            
            // Check if monster is alive
            if (monster.hitPoints <= 0) {
                return false;
            }
            
            // Check if monster is in range (reasonable attack range)
            Point monsterPos = monster.position.tile;
            Point playerPos = player->position.tile;
            int dx = std::abs(monsterPos.x - playerPos.x);
            int dy = std::abs(monsterPos.y - playerPos.y);
            
            // Allow attacking monsters within 15 tiles
            if (dx > 15 || dy > 15) {
                return false;
            }
            
            // Use appropriate attack command based on weapon type
            int controlled_id = GetControlledPlayerId();
            
            // Direct execution for companions
            if (controlled_id != MyPlayerId) {
                std::cerr << "GAP: Using direct attack for companion " << controlled_id << std::endl;
                return ExecuteDirectAttack(controlled_id, monsterId);
            } else if (gbIsMultiplayer) {
                // Network command for main player in multiplayer
                if (player->UsesRangedWeapon()) {
                    NetSendCmdParam1ForPlayer(controlled_id, true, CMD_RATTACKID, monsterId);
                } else {
                    NetSendCmdParam1ForPlayer(controlled_id, true, CMD_ATTACKID, monsterId);
                }
            } else {
                // Single player main character - use standard commands
                if (player->UsesRangedWeapon()) {
                    NetSendCmdParam1(true, CMD_RATTACKID, monsterId);
                } else {
                    NetSendCmdParam1(true, CMD_ATTACKID, monsterId);
                }
            }
            
            return true;
        }
    } else {
        // Attack a position (x, y) - useful for ranged attacks without pathfinding
        Point target(x, y);

        if (!InDungeonBounds(target)) {
            return false;
        }

        int controlled_id = GetControlledPlayerId();

        // For companions, we need to find the monster at/near this position and attack by ID
        // Network position commands don't work reliably for companions
        if (controlled_id != MyPlayerId) {
            // Find monster at or near target position (within 2 tiles)
            // Monsters move between ticks, so we need fuzzy matching
            int targetMonsterId = -1;
            int minDistance = 3; // Allow up to 2 tiles away

            for (size_t i = 0; i < ActiveMonsterCount; i++) {
                const auto& monster = Monsters[ActiveMonsters[i]];
                if (monster.hitPoints > 0) {
                    int dx = std::abs(monster.position.tile.x - target.x);
                    int dy = std::abs(monster.position.tile.y - target.y);
                    int dist = std::max(dx, dy); // Chebyshev distance

                    if (dist < minDistance) {
                        minDistance = dist;
                        targetMonsterId = ActiveMonsters[i];
                    }
                }
            }

            if (targetMonsterId >= 0) {
                const auto& foundMonster = Monsters[targetMonsterId];
                std::cerr << "GAP: Position attack (" << x << "," << y << ") → Found monster "
                          << targetMonsterId << " at (" << foundMonster.position.tile.x << ","
                          << foundMonster.position.tile.y << ") search_dist=" << minDistance << std::endl;
                return ExecuteDirectAttack(controlled_id, targetMonsterId);
            } else {
                std::cerr << "GAP: Position attack failed - no monster near (" << x << "," << y << ")" << std::endl;
                return false;
            }
        } else {
            // Main player - use network command
            if (player->UsesRangedWeapon()) {
                NetSendCmdLocForPlayer(controlled_id, true, CMD_RATTACKXY, target);
            } else {
                NetSendCmdLocForPlayer(controlled_id, true, CMD_SATTACKXY, target);
            }
            return true;
        }
    }
    
    return false;
}

bool GapIntentProcessor::ExecuteCast(int slot, int x, int y) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP: ExecuteCast failed - no controlled player" << std::endl;
        return false;
    }

    // Allow scroll use in more states than standing (similar to potion use)
    if (player->_pmode == PM_DEATH || player->_pmode == PM_QUIT || player->_pmode == PM_NEWLVL) {
        std::cerr << "GAP: ExecuteCast failed - invalid player mode (" << player->_pmode << ")" << std::endl;
        return false;
    }

    // Validate belt slot
    if (slot < 0 || slot >= MaxBeltItems) {
        std::cerr << "GAP: ExecuteCast failed - invalid belt slot " << slot << std::endl;
        return false;
    }

    // Check if slot has a scroll
    const Item& beltItem = player->SpdList[slot];
    if (beltItem.isEmpty()) {
        std::cerr << "GAP: ExecuteCast failed - belt slot " << slot << " is empty" << std::endl;
        return false;
    }

    // Verify it's a scroll
    if (beltItem._iMiscId != IMISC_SCROLL && beltItem._iMiscId != IMISC_SCROLLT) {
        std::cerr << "GAP: ExecuteCast failed - belt slot " << slot << " is not a scroll" << std::endl;
        return false;
    }

    std::cout << "GAP: Using scroll " << beltItem._iIName
              << " (spell=" << static_cast<int>(beltItem._iSpell) << ")"
              << " from belt slot " << slot << std::endl;

    // Use the belt item (INVITEM_BELT_FIRST = 47, so slot 0 = inv index 47)
    int invIndex = INVITEM_BELT_FIRST + slot;

    // UseInvItem handles scroll consumption and spell casting
    bool success = UseInvItem(*player, invIndex);

    if (success) {
        std::cout << "GAP: Successfully used scroll from slot " << slot << std::endl;
    } else {
        std::cerr << "GAP: UseInvItem returned FALSE for scroll at slot " << slot << std::endl;
    }

    return success;
}

bool GapIntentProcessor::ExecutePickup(int item_id) {
    int player_id = GetControlledPlayerId();

    // Use direct pickup execution for companions (bypasses network routing bug)
    return gap::ExecuteDirectPickup(player_id, item_id);
}

bool GapIntentProcessor::ExecuteUsePotion(const std::string& kind, int slot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP: ExecuteUsePotion failed - no controlled player" << std::endl;
        return false;
    }

    std::cout << "GAP: ExecuteUsePotion - Player " << player->getId()
              << " (" << player->_pName << ") attempting to use slot " << slot
              << ", HP=" << (player->_pHitPoints >> 6) << "/" << (player->_pMaxHP >> 6)
              << ", mode=" << player->_pmode << std::endl;

    // Allow potion use in most modes (like real player)
    // Block only during death/quit/newlvl transitions
    if (player->_pmode == PM_DEATH || player->_pmode == PM_QUIT || player->_pmode == PM_NEWLVL) {
        std::cerr << "GAP: ExecuteUsePotion failed - invalid player mode (" << player->_pmode << ")" << std::endl;
        return false;
    }

    // Validate belt slot
    if (slot < 0 || slot >= MaxBeltItems) {
        std::cerr << "GAP: Invalid belt slot " << slot << " (must be 0-" << (MaxBeltItems-1) << ")" << std::endl;
        return false;
    }

    // Check if slot has an item
    const Item& beltItem = player->SpdList[slot];
    std::cout << "GAP: Belt slot " << slot << " - isEmpty=" << beltItem.isEmpty()
              << ", itype=" << static_cast<int>(beltItem._itype)
              << ", name='" << (beltItem.isEmpty() ? "empty" : beltItem._iIName) << "'" << std::endl;

    if (beltItem.isEmpty()) {
        std::cerr << "GAP: Belt slot " << slot << " is empty" << std::endl;
        return false;
    }

    // Dump full belt state for debugging
    std::cout << "GAP: Full belt state for player " << player->getId() << ": ";
    for (int i = 0; i < MaxBeltItems; i++) {
        const Item& item = player->SpdList[i];
        if (item.isEmpty()) {
            std::cout << "[" << i << ":empty] ";
        } else {
            std::cout << "[" << i << ":" << item._iIName << "] ";
        }
    }
    std::cout << std::endl;

    // Use the belt item (INVITEM_BELT_FIRST = 47, so slot 0 = inv index 47)
    int invIndex = INVITEM_BELT_FIRST + slot;

    std::cout << "GAP: Using belt item at slot " << slot
              << " (inv index " << invIndex << ")"
              << " - " << beltItem._iIName << std::endl;

    // Call the game's UseInvItem function
    // This handles all the logic: consuming the item, applying effects, etc.
    bool success = UseInvItem(*player, invIndex);

    if (success) {
        std::cout << "GAP: Successfully used belt item at slot " << slot
                  << ", new HP=" << (player->_pHitPoints >> 6) << "/" << (player->_pMaxHP >> 6)
                  << std::endl;
    } else {
        std::cerr << "GAP: UseInvItem returned FALSE for slot " << slot << std::endl;
    }

    return success;
}

bool GapIntentProcessor::ExecuteInteract(int object_id) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        return false;
    }
    
    if (player->_pmode != PM_STAND) {
        return false;
    }
    
    // Find the object in the active objects list
    for (int i = 0; i < ActiveObjectCount; i++) {
        if (ActiveObjects[i] == object_id) {
            const auto& obj = Objects[object_id];
            
            // Check if object is within range (adjacent)
            Point objPos = obj.position;
            Point playerPos = player->position.tile;
            int dx = std::abs(objPos.x - playerPos.x);
            int dy = std::abs(objPos.y - playerPos.y);
            
            if (dx <= 1 && dy <= 1) {
                // Use existing object interaction with correct player routing
                int controlled_id = GetControlledPlayerId();
                NetSendCmdLocForPlayer(controlled_id, true, CMD_OPOBJXY, objPos);
                return true;
            }
        }
    }
    
    return false;
}

bool GapIntentProcessor::ExecutePath(int x, int y) {
    // Path intent is similar to move but implies longer distance pathfinding
    // For now, delegate to ExecuteMove - pathfinding improvements will come later
    return ExecuteMove(x, y);
}

bool GapIntentProcessor::ExecuteExplore() {
    // Explore intent means "move to next unexplored area"
    // For now, return false - this will be implemented with frontier detection
    std::cerr << "GAP: Exploration not yet implemented - needs frontier detection" << std::endl;
    return false;
}

bool GapIntentProcessor::ExecuteChat(const std::string& message) {
    // Send a chat message from the AI agent
#ifdef ENABLE_GAP
    const size_t MAX_CHAT_LENGTH = 150;  // Match Python's chat.py splitting (line 201)
    
    if (message.length() <= MAX_CHAT_LENGTH) {
        // Message fits in one line
        GAPChatHandler::getInstance().SendAIResponse(message);
    } else {
        // Break long message into chunks
        size_t pos = 0;
        int fragment = 1;
        
        while (pos < message.length()) {
            // Find a good break point (space) near the limit
            size_t chunkEnd = pos + MAX_CHAT_LENGTH;
            if (chunkEnd > message.length()) {
                chunkEnd = message.length();
            } else {
                // Look for last space before limit to avoid breaking words
                size_t lastSpace = message.rfind(' ', chunkEnd);
                if (lastSpace != std::string::npos && lastSpace > pos) {
                    chunkEnd = lastSpace;
                }
            }
            
            std::string chunk = message.substr(pos, chunkEnd - pos);
            
            // Add continuation marker for multi-part messages
            if (fragment > 1 || chunkEnd < message.length()) {
                if (fragment == 1) {
                    chunk += "...";
                } else if (chunkEnd < message.length()) {
                    chunk = "..." + chunk + "...";
                } else {
                    chunk = "..." + chunk;
                }
            }
            
            GAPChatHandler::getInstance().SendAIResponse(chunk);
            
            pos = chunkEnd;
            // Skip the space we broke on
            if (pos < message.length() && message[pos] == ' ') {
                pos++;
            }
            fragment++;
        }
    }
    return true;
#else
    std::cerr << "GAP: Chat intent requires ENABLE_GAP flag" << std::endl;
    return false;
#endif
}

#ifdef ENABLE_GAP
void GapIntentProcessor::ProcessPendingIntentsViaSeat(uint32_t current_tick) {
    // Process GAP intents through the new Seat system instead of direct execution
    // NOTE: Chat intents are handled globally at the GAP protocol level and never reach here
    auto& seatManager = devilution::SeatManager::Instance();
    
    while (!intent_queue_.empty()) {
        const Intent& gap_intent = intent_queue_.front();

        if (gap_intent.target_tick > 0 && gap_intent.target_tick > current_tick) {
            break; // Wait for target tick
        }

        // Some actions should be executed directly, not through the Seat system
        // These include: stats, shopping, identification, inventory management, dropping items, etc.
        bool use_direct_execution = (
            gap_intent.action == "addstat" ||
            gap_intent.action == "buy" ||
            gap_intent.action == "sell" ||
            gap_intent.action == "repair" ||
            gap_intent.action == "identify" ||
            gap_intent.action == "belt_refill" ||
            gap_intent.action == "drop_item" ||
            gap_intent.action == "drop_gold"
        );

        if (use_direct_execution) {
            // Execute directly without going through Seat system
            if (ExecuteIntent(gap_intent)) {
                std::cout << "GAP: Executed " << gap_intent.action << " intent directly" << std::endl;
            } else {
                std::cerr << "GAP: Failed to execute " << gap_intent.action << " intent" << std::endl;
            }
        } else {
            // Convert GAP intent to Seat intent for movement/combat actions
            devilution::Intent seat_intent = ConvertToSeatIntent(gap_intent, current_tick);

            // Get the companion seat for the controlled player
            int controlled_player = GapCore::Instance().GetControlledPlayer();
            auto* seat = seatManager.GetSeat(controlled_player);

            if (auto* companion_seat = dynamic_cast<devilution::CompanionSeat*>(seat)) {
                companion_seat->EnqueueIntent(seat_intent);
                std::cout << "GAP: Bridged " << gap_intent.action << " intent to CompanionSeat for player " << controlled_player << std::endl;
            } else {
                std::cerr << "GAP: No CompanionSeat found for player " << controlled_player << ", using direct execution" << std::endl;
                // Fallback to direct execution
                ExecuteIntent(gap_intent);
            }
        }

        intent_queue_.pop();
    }
}

devilution::Intent GapIntentProcessor::ConvertToSeatIntent(const Intent& gap_intent, uint64_t tick) {
    // Convert GAP intent format to Seat intent format
    if (gap_intent.action == "move") {
        return devilution::Intent(devilution::Intent::Type::Move, tick, 
                                 gap_intent.param_x, gap_intent.param_y);
    } else if (gap_intent.action == "attack") {
        return devilution::Intent(devilution::Intent::Type::Attack, tick,
                                 gap_intent.param_x, gap_intent.param_y, gap_intent.param_id);
    } else if (gap_intent.action == "pickup") {
        // Pickup is Interact with item_id in param1
        return devilution::Intent(devilution::Intent::Type::Interact, tick,
                                 gap_intent.param_x, gap_intent.param_y, gap_intent.param_id);
    } else if (gap_intent.action == "use_potion") {
        return devilution::Intent(devilution::Intent::Type::UseItem, tick,
                                 0, 0, gap_intent.param_slot);
    } else if (gap_intent.action == "cast") {
        return devilution::Intent(devilution::Intent::Type::Cast, tick,
                                 gap_intent.param_x, gap_intent.param_y, gap_intent.param_slot);
    } else if (gap_intent.action == "interact") {
        return devilution::Intent(devilution::Intent::Type::Interact, tick,
                                 gap_intent.param_x, gap_intent.param_y);
    } else if (gap_intent.action == "chat") {
        return devilution::Intent(devilution::Intent::Type::Chat, tick,
                                 gap_intent.param_kind);
    } else {
        // Default to move for unknown actions
        std::cerr << "GAP: Unknown action '" << gap_intent.action << "', defaulting to move" << std::endl;
        return devilution::Intent(devilution::Intent::Type::Move, tick,
                                 gap_intent.param_x, gap_intent.param_y);
    }
}

bool GapIntentProcessor::ExecuteBuy(const std::string& npcCode, int itemIndex) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Store: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Map NPC code to _talker_id
    _talker_id npcType;
    if (npcCode == "sm") {
        npcType = TOWN_SMITH;
    } else if (npcCode == "hl") {
        npcType = TOWN_HEALER;
    } else if (npcCode == "wt") {
        npcType = TOWN_WITCH;
    } else if (npcCode == "pg") {
        npcType = TOWN_PEGBOY;
    } else {
        std::cerr << "GAP Store: Unknown NPC code: " << npcCode << std::endl;
        return false;
    }

    return CompanionBuyItem(*player, npcType, itemIndex);
}

bool GapIntentProcessor::ExecuteSell(int invSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Store: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    return CompanionSellItem(*player, invSlot);
}

bool GapIntentProcessor::ExecuteRepair(int invSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Store: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    return CompanionRepairItem(*player, invSlot);
}

bool GapIntentProcessor::ExecuteIdentify(int invSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Store: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    return CompanionIdentifyItem(*player, invSlot);
}

bool GapIntentProcessor::ExecuteAddStat(const std::string& statName) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Stats: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Check if player has stat points available
    if (player->_pStatPts <= 0) {
        std::cerr << "GAP Stats: No stat points available" << std::endl;
        return false;
    }

    // Apply stat increase
    if (statName == "STR") {
        ModifyPlrStr(*player, 1);
        std::cout << "GAP Stats: Added 1 point to STR" << std::endl;
    } else if (statName == "DEX") {
        ModifyPlrDex(*player, 1);
        std::cout << "GAP Stats: Added 1 point to DEX" << std::endl;
    } else if (statName == "MAG") {
        ModifyPlrMag(*player, 1);
        std::cout << "GAP Stats: Added 1 point to MAG" << std::endl;
    } else if (statName == "VIT") {
        ModifyPlrVit(*player, 1);
        std::cout << "GAP Stats: Added 1 point to VIT" << std::endl;
    } else {
        std::cerr << "GAP Stats: Unknown stat name: " << statName << std::endl;
        return false;
    }

    // Deduct stat point
    player->_pStatPts--;

    std::cout << "GAP Stats: Stat points remaining: " << player->_pStatPts << std::endl;

    return true;
}

bool GapIntentProcessor::ExecuteBeltRefill(int invSlot, int beltSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Belt: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Validate inventory slot
    if (invSlot < 0 || invSlot >= player->_pNumInv) {
        std::cerr << "GAP Belt: Invalid inventory slot: " << invSlot << std::endl;
        return false;
    }

    // Validate belt slot
    if (beltSlot < 0 || beltSlot >= MaxBeltItems) {
        std::cerr << "GAP Belt: Invalid belt slot: " << beltSlot << std::endl;
        return false;
    }

    // Check if inventory slot has a consumable item
    const Item& invItem = player->InvList[invSlot];
    if (invItem.isEmpty()) {
        std::cerr << "GAP Belt: Inventory slot " << invSlot << " is empty" << std::endl;
        return false;
    }

    // Check if item can be placed on belt (1x1 consumables only)
    if (!CanBePlacedOnBelt(*player, invItem)) {
        std::cerr << "GAP Belt: Item in slot " << invSlot << " cannot be placed on belt" << std::endl;
        return false;
    }

    // Check if belt slot is empty
    if (!player->SpdList[beltSlot].isEmpty()) {
        std::cerr << "GAP Belt: Belt slot " << beltSlot << " is not empty" << std::endl;
        return false;
    }

    // Move item from inventory to belt
    player->SpdList[beltSlot] = invItem;
    player->RemoveInvItem(invSlot, false);  // Don't calc scrolls yet
    player->CalcScrolls();  // Recalculate scrolls after belt update
    RedrawComponent(PanelDrawComponent::Belt);

    // Network sync
    int controlled_id = GetControlledPlayerId();
    if (controlled_id == MyPlayerId) {
        NetSendCmdChBeltItem(false, beltSlot);
    }

    std::cout << "GAP Belt: Moved item from inv slot " << invSlot
              << " to belt slot " << beltSlot << std::endl;

    return true;
}

bool GapIntentProcessor::ExecuteDropItem(int invSlot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Drop: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Validate inventory slot
    if (invSlot < 0 || invSlot >= player->_pNumInv) {
        std::cerr << "GAP Drop: Invalid inventory slot: " << invSlot << std::endl;
        return false;
    }

    // Check if inventory slot has an item
    const Item& invItem = player->InvList[invSlot];
    if (invItem.isEmpty()) {
        std::cerr << "GAP Drop: Inventory slot " << invSlot << " is empty" << std::endl;
        return false;
    }

    // Find adjacent position to drop the item
    std::optional<Point> dropPosition = FindAdjacentPositionForItem(
        player->position.tile,
        player->_pdir
    );

    if (!dropPosition) {
        std::cerr << "GAP Drop: No adjacent position available to drop item" << std::endl;
        return false;
    }

    // Drop the item
    std::cout << "GAP Drop: Dropping " << invItem._iIName
              << " from slot " << invSlot
              << " at (" << dropPosition->x << "," << dropPosition->y << ")" << std::endl;

    // Send network command to drop item
    // CMD_PUTITEM is used to place items from cursor onto ground
    NetSendCmdPItem(true, CMD_PUTITEM, *dropPosition, invItem);

    // Remove item from inventory
    player->RemoveInvItem(invSlot, true);  // Recalculate scrolls

    return true;
}

bool GapIntentProcessor::ExecuteDropGold(int amount) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        std::cerr << "GAP Drop Gold: GetControlledPlayer() returned nullptr" << std::endl;
        return false;
    }

    // Validate gold amount
    if (amount <= 0) {
        std::cerr << "GAP Drop Gold: Invalid amount: " << amount << std::endl;
        return false;
    }

    // Check if player has enough gold
    if (player->_pGold < amount) {
        std::cerr << "GAP Drop Gold: Not enough gold (has " << player->_pGold
                  << ", wants to drop " << amount << ")" << std::endl;
        return false;
    }

    // Find adjacent position to drop the gold
    std::optional<Point> dropPosition = FindAdjacentPositionForItem(
        player->position.tile,
        player->_pdir
    );

    if (!dropPosition) {
        std::cerr << "GAP Drop Gold: No adjacent position available" << std::endl;
        return false;
    }

    // Create a gold item
    Item goldItem;
    MakeGoldStack(goldItem, amount);

    std::cout << "GAP Drop Gold: Dropping " << amount << " gold at ("
              << dropPosition->x << "," << dropPosition->y << ")" << std::endl;

    // Drop the gold
    NetSendCmdPItem(true, CMD_PUTITEM, *dropPosition, goldItem);

    // Deduct gold from player
    player->_pGold -= amount;

    return true;
}

#endif

} // namespace devilution::gap