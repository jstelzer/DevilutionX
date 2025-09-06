#ifdef ENABLE_GAP

#include "player_actor.h"
#include "../diablo.h"
#include "../levels/town.h"
#include "../control.h"
#include "../engine/point.hpp"
#include "../nthread.h"
#include "../gap/gap_network.h"  // For companion command routing
#include <cmath>
#include <algorithm>

namespace devilution {

PlayerActor::PlayerActor(int player_index) 
    : player_index_(player_index), player_(nullptr) {
    // Validate player index
    if (player_index >= 0 && player_index < MAX_PLRS) {
        player_ = &Players[player_index];
    }
}

bool PlayerActor::IsValid() const {
    return player_ != nullptr && player_index_ >= 0 && player_index_ < MAX_PLRS &&
           Players[player_index_].plractive;
}

// === Actor Interface Implementation ===

ActorId PlayerActor::GetId() const {
    return ActorIds::ForPlayer(player_index_);
}

const char* PlayerActor::GetName() const {
    if (!IsValid()) return "";
    return player_->_pName;
}

const char* PlayerActor::GetTypeName() const {
    return "Player";
}

Point PlayerActor::GetPosition() const {
    if (!IsValid()) return {0, 0};
    return player_->position.tile;
}

Point PlayerActor::GetFuturePosition() const {
    if (!IsValid()) return {0, 0};
    return player_->position.future;
}

int PlayerActor::GetLevel() const {
    if (!IsValid()) return 0;
    return static_cast<int>(player_->plrlevel);
}

int PlayerActor::GetHitPoints() const {
    if (!IsValid()) return 0;
    return player_->_pHitPoints >> 6; // Convert from fixed point
}

int PlayerActor::GetMaxHitPoints() const {
    if (!IsValid()) return 0;
    return player_->_pMaxHP >> 6; // Convert from fixed point
}

bool PlayerActor::IsAlive() const {
    return IsValid() && player_->_pHitPoints > 0;
}

bool PlayerActor::IsActive() const {
    return IsValid(); // For players, valid == active
}

int PlayerActor::GetArmorClass() const {
    if (!IsValid()) return 0;
    return player_->_pIAC; // Player's total armor class
}

bool PlayerActor::IsPlayerMinion() const {
    return false; // Players are never minions
}

// === Command Interface ===

bool PlayerActor::CanReceiveCommands() const {
    return IsValid(); // All valid players can receive commands
}

void PlayerActor::MoveTo(Point target) {
    if (!IsValid()) return;
    
    // Milestone C1: Route through existing pathfinding system
    // This is the same logic used in GAP intent processing
    if (player_->_pmode != PM_STAND) {
        return; // Can't move while doing something else
    }
    
    if (!InDungeonBounds(target)) {
        return; // Invalid target
    }
    
    if (player_->position.tile == target) {
        return; // Already at target
    }
    
    // Use the game's pathfinding system
    MakePlrPath(*player_, target, true);
    player_->destAction = ACTION_WALK;
    
    // Send network command if needed (multiplayer)  
    if (gbIsMultiplayer) {
        // Use GAP network routing for proper player isolation
        gap::NetSendCmdLocForPlayer(player_index_, true, CMD_WALKXY, target);
    }
}

void PlayerActor::AttackTarget(ActorId target) {
    if (!IsValid()) return;
    
    // Convert ActorId back to legacy format for existing systems
    if (ActorIds::IsMonster(target)) {
        int monster_index = ActorIds::GetMonsterIndex(target);
        
        // Validate monster
        if (monster_index < 0 || static_cast<size_t>(monster_index) >= MaxMonsters) {
            return;
        }
        
        // Use GAP network routing for proper player isolation
        if (player_->UsesRangedWeapon()) {
            gap::NetSendCmdParam1ForPlayer(player_index_, true, CMD_RATTACKID, monster_index);
        } else {
            gap::NetSendCmdParam1ForPlayer(player_index_, true, CMD_ATTACKID, monster_index);
        }
    } else if (ActorIds::IsPlayer(target)) {
        // For PvP - attack player position
        int target_player = ActorIds::GetPlayerIndex(target);
        if (target_player >= 0 && target_player < MAX_PLRS && Players[target_player].plractive) {
            Point pos = Players[target_player].position.tile;
            AttackPosition(pos);
        }
    }
}

void PlayerActor::AttackPosition(Point target) {
    if (!IsValid()) return;
    
    if (!InDungeonBounds(target)) {
        return; // Invalid target
    }
    
    // Use GAP network routing for proper player isolation
    if (player_->UsesRangedWeapon()) {
        gap::NetSendCmdLocForPlayer(player_index_, true, CMD_RATTACKXY, target);
    } else {
        gap::NetSendCmdLocForPlayer(player_index_, true, CMD_SATTACKXY, target);
    }
}

void PlayerActor::InteractWithObject(int object_id) {
    if (!IsValid()) return;
    
    // Validate object exists
    bool object_found = false;
    Point object_pos;
    
    for (int i = 0; i < ActiveObjectCount; i++) {
        if (ActiveObjects[i] == object_id) {
            object_pos = Objects[object_id].position;
            object_found = true;
            break;
        }
    }
    
    if (!object_found) {
        return; // Object doesn't exist
    }
    
    // Check if object is within interaction range
    Point player_pos = GetPosition();
    int dx = std::abs(object_pos.x - player_pos.x);
    int dy = std::abs(object_pos.y - player_pos.y);
    
    if (dx > 1 || dy > 1) {
        return; // Too far away
    }
    
    // Use GAP network routing for proper player isolation
    gap::NetSendCmdLocForPlayer(player_index_, true, CMD_OPOBJXY, object_pos);
}

// === Player-Specific Extensions ===

int PlayerActor::GetMana() const {
    if (!IsValid()) return 0;
    return player_->_pMana >> 6; // Convert from fixed point
}

int PlayerActor::GetMaxMana() const {
    if (!IsValid()) return 0;
    return player_->_pMaxMana >> 6; // Convert from fixed point
}

bool PlayerActor::IsInTown() const {
    if (!IsValid()) return false;
    return leveltype == DTYPE_TOWN;
}

const Item* PlayerActor::GetBeltItem(int slot) const {
    if (!IsValid() || slot < 0 || slot >= MaxBeltItems) return nullptr;
    const Item& item = player_->SpdList[slot];
    return item.isEmpty() ? nullptr : &item;
}


} // namespace devilution

#endif // ENABLE_GAP