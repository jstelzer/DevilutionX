#include "gap_intent.h"
#include "gap_json.h"
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
    if (MyPlayerId >= MAX_PLRS) {
        return false;
    }
    
    auto& player = Players[MyPlayerId];
    
    if (player._pmode != PM_STAND) {
        return false;
    }
    
    Point target(x, y);
    
    if (!InDungeonBounds(target)) {
        return false;
    }
    
    if (player.position.tile == target) {
        return false; // Already at target
    }
    
    // Use the game's pathfinding system like the normal controls do
    MakePlrPath(player, target, true);
    player.destAction = ACTION_WALK;
    
    // Send network command for multiplayer compatibility
    if (gbIsMultiplayer) {
        NetSendCmdLoc(player.getId(), true, CMD_WALKXY, target);
    }
    
    return true;
}

bool GapIntentProcessor::ExecuteAttack(int x, int y) {
    if (MyPlayerId >= MAX_PLRS) {
        return false;
    }
    
    auto& player = Players[MyPlayerId];
    
    if (player._pmode != PM_STAND) {
        return false;
    }
    
    // Check if we have a monster ID passed as x (when y is -1)
    // This allows attacking specific monsters by ID
    if (y == -1) {
        int monsterId = x;
        if (monsterId >= 0 && monsterId < MaxMonsters) {
            const auto& monster = Monsters[monsterId];
            
            // Check if monster is alive
            if (monster.hitPoints <= 0) {
                return false;
            }
            
            // Check if monster is in range (reasonable attack range)
            Point monsterPos = monster.position.tile;
            Point playerPos = player.position.tile;
            int dx = std::abs(monsterPos.x - playerPos.x);
            int dy = std::abs(monsterPos.y - playerPos.y);
            
            // Allow attacking monsters within 15 tiles
            if (dx > 15 || dy > 15) {
                return false;
            }
            
            // Use appropriate attack command based on weapon type
            if (player.UsesRangedWeapon()) {
                NetSendCmdParam1(true, CMD_RATTACKID, monsterId);
            } else {
                NetSendCmdParam1(true, CMD_ATTACKID, monsterId);
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
        if (player.UsesRangedWeapon()) {
            NetSendCmdLoc(MyPlayerId, true, CMD_RATTACKXY, target);
        } else {
            NetSendCmdLoc(MyPlayerId, true, CMD_SATTACKXY, target);
        }
        
        return true;
    }
    
    return false;
}

bool GapIntentProcessor::ExecuteCast(int slot, int x, int y) {
    if (MyPlayerId >= MAX_PLRS) {
        return false;
    }
    
    auto& player = Players[MyPlayerId];
    
    if (player._pmode != PM_STAND) {
        return false;
    }
    
    // For now, return false - spell casting needs deeper integration
    // TODO: Implement spell casting by slot
    std::cerr << "GAP: Spell casting not yet implemented" << std::endl;
    return false;
}

bool GapIntentProcessor::ExecutePickup(int item_id) {
    if (MyPlayerId >= MAX_PLRS) {
        return false;
    }
    
    auto& player = Players[MyPlayerId];
    
    if (player._pmode != PM_STAND) {
        return false;
    }
    
    // Find the item in the active items list
    for (uint8_t i = 0; i < ActiveItemCount; i++) {
        if (ActiveItems[i] == item_id) {
            const auto& item = Items[item_id];
            
            // Check if item is within reasonable range (adjacent)
            Point itemPos = item.position;
            Point playerPos = player.position.tile;
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
    if (MyPlayerId >= MAX_PLRS) {
        return false;
    }
    
    auto& player = Players[MyPlayerId];
    
    if (player._pmode != PM_STAND) {
        return false;
    }
    
    // For now, return false - potion use needs deeper integration  
    // TODO: Implement potion usage from belt/inventory
    std::cerr << "GAP: Potion usage not yet implemented" << std::endl;
    return false;
}

bool GapIntentProcessor::ExecuteInteract(int object_id) {
    if (MyPlayerId >= MAX_PLRS) {
        return false;
    }
    
    auto& player = Players[MyPlayerId];
    
    if (player._pmode != PM_STAND) {
        return false;
    }
    
    // Find the object in the active objects list
    for (int i = 0; i < ActiveObjectCount; i++) {
        if (ActiveObjects[i] == object_id) {
            const auto& obj = Objects[object_id];
            
            // Check if object is within range (adjacent)
            Point objPos = obj.position;
            Point playerPos = player.position.tile;
            int dx = std::abs(objPos.x - playerPos.x);
            int dy = std::abs(objPos.y - playerPos.y);
            
            if (dx <= 1 && dy <= 1) {
                // Use existing object interaction
                NetSendCmdLoc(MyPlayerId, true, CMD_OPOBJXY, objPos);
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