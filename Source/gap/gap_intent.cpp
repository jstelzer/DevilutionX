#include "gap_intent.h"
#include "gap_json.h"
#include "../player.h"
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
    
    Point target(x, y);
    
    if (!InDungeonBounds(target)) {
        return false;
    }
    
    return false;
}

} // namespace devilution::gap