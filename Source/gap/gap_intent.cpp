#include "gap_intent.h"
#include "gap_json.h"
#include "../player.h"
#include "../monster.h"
#include "../cursor.h"
#include "../control.h"
#include "../engine/point.hpp"
#include "../levels/gendung.h"
#include "../nthread.h"
#include "../msg.h"
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
    } else if (intent.action == "use_potion") {
        return false;
    } else if (intent.action == "pickup") {
        return false;
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

} // namespace devilution::gap