#include "gap_intent.h"
#include "gap_json.h"
#include "gap_core.h"
#include "gap_network.h"
#ifdef ENABLE_GAP
#include "gap_chat.h"
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
#include <iostream>

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
    intent.action = intent_msg.GetString("action");
    
    std::string params_str = intent_msg.GetObjectString("params");
    JsonParser params(params_str);
    intent.param_x = params.GetInt("x");
    intent.param_y = params.GetInt("y");
    intent.param_id = params.GetInt("id");
    intent.param_slot = params.GetInt("slot");
    intent.param_kind = params.GetString("kind");
    
    intent.target_tick = intent_msg.GetInt("target_tick");
    
    intent_queue_.push(intent);
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
        return ExecuteAttack(intent.param_x, intent.param_y);
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
    
    if (player->_pmode != PM_STAND) {
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
        // Attack a position (x, y) - useful for area attacks
        Point target(x, y);
        
        if (!InDungeonBounds(target)) {
            return false;
        }
        
        // Use appropriate attack command for position
        int controlled_id = GetControlledPlayerId();
        if (player->UsesRangedWeapon()) {
            NetSendCmdLocForPlayer(controlled_id, true, CMD_RATTACKXY, target);
        } else {
            NetSendCmdLocForPlayer(controlled_id, true, CMD_SATTACKXY, target);
        }
        
        return true;
    }
    
    return false;
}

bool GapIntentProcessor::ExecuteCast(int slot, int x, int y) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        return false;
    }
    
    if (player->_pmode != PM_STAND) {
        return false;
    }
    
    // For now, return false - spell casting needs deeper integration
    // TODO: Implement spell casting by slot
    std::cerr << "GAP: Spell casting not yet implemented" << std::endl;
    return false;
}

bool GapIntentProcessor::ExecutePickup(int item_id) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        return false;
    }
    
    if (player->_pmode != PM_STAND) {
        return false;
    }
    
    // Find the item in the active items list
    for (uint8_t i = 0; i < ActiveItemCount; i++) {
        if (ActiveItems[i] == item_id) {
            const auto& item = Items[item_id];
            
            // Check if item is within reasonable range (adjacent)
            Point itemPos = item.position;
            Point playerPos = player->position.tile;
            int dx = std::abs(itemPos.x - playerPos.x);
            int dy = std::abs(itemPos.y - playerPos.y);
            
            if (dx <= 1 && dy <= 1) {
                // Use existing pickup mechanism
                NetSendCmdPItem(true, CMD_REQUESTGITEM, itemPos, item);
                return true;
            }
        }
    }
    
    return false;
}

bool GapIntentProcessor::ExecuteUsePotion(const std::string& kind, int slot) {
    Player* player = GetControlledPlayer();
    if (player == nullptr) {
        return false;
    }
    
    if (player->_pmode != PM_STAND) {
        return false;
    }
    
    // For now, return false - potion use needs deeper integration  
    // TODO: Implement potion usage from belt/inventory
    std::cerr << "GAP: Potion usage not yet implemented" << std::endl;
    return false;
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
    const size_t MAX_CHAT_LENGTH = 100;  // Maximum characters per message
    
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

} // namespace devilution::gap