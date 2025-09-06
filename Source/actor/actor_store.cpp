#ifdef ENABLE_GAP

#include "actor_store.h"
#include "../diablo.h"
#include <iostream>

namespace devilution {

void ActorStore::Initialize() {
    if (initialized_) {
        return;
    }
    
    std::cout << "ActorStore: Initializing actor registry" << std::endl;
    
    // Create PlayerActor instances for all player slots
    for (int i = 0; i < MAX_PLRS; i++) {
        ActorId id = ActorIds::ForPlayer(i);
        player_actors_[id] = std::make_unique<PlayerActor>(i);
    }
    
    initialized_ = true;
    std::cout << "ActorStore: Initialized with " << MAX_PLRS << " player slots" << std::endl;
}

void ActorStore::Shutdown() {
    if (!initialized_) {
        return;
    }
    
    std::cout << "ActorStore: Shutting down actor registry" << std::endl;
    
    player_actors_.clear();
    // TODO: Milestone C2 - Clear monster actors
    
    initialized_ = false;
}

void ActorStore::Refresh() {
    if (!initialized_) {
        return;
    }
    
    // Note: PlayerActor instances validate themselves via IsValid()
    // So no refresh needed for Milestone C1. 
    // 
    // TODO: Milestone C2 - Refresh monster actor list based on ActiveMonsters
}

// === Unified Lookups ===

Actor* ActorStore::GetActor(ActorId id) {
    if (!initialized_) {
        return nullptr;
    }
    
    if (ActorIds::IsPlayer(id)) {
        auto it = player_actors_.find(id);
        return (it != player_actors_.end()) ? it->second.get() : nullptr;
    }
    
    // TODO: Milestone C2 - Add monster lookup
    // if (ActorIds::IsMonster(id)) {
    //     auto it = monster_actors_.find(id);
    //     return (it != monster_actors_.end()) ? it->second.get() : nullptr;
    // }
    
    return nullptr;
}

const Actor* ActorStore::GetActor(ActorId id) const {
    return const_cast<ActorStore*>(this)->GetActor(id);
}

// === Type-Specific Lookups ===

PlayerActor* ActorStore::GetPlayerActor(int player_index) {
    if (!initialized_ || player_index < 0 || player_index >= MAX_PLRS) {
        return nullptr;
    }
    
    ActorId id = ActorIds::ForPlayer(player_index);
    auto it = player_actors_.find(id);
    return (it != player_actors_.end()) ? it->second.get() : nullptr;
}

const PlayerActor* ActorStore::GetPlayerActor(int player_index) const {
    return const_cast<ActorStore*>(this)->GetPlayerActor(player_index);
}

// === Iteration ===

void ActorStore::ForEachActivePlayer(std::function<void(PlayerActor&)> callback) {
    if (!initialized_ || !callback) {
        return;
    }
    
    for (auto& pair : player_actors_) {
        PlayerActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            callback(*actor);
        }
    }
}

void ActorStore::ForEachActivePlayer(std::function<void(const PlayerActor&)> callback) const {
    if (!initialized_ || !callback) {
        return;
    }
    
    for (const auto& pair : player_actors_) {
        const PlayerActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            callback(*actor);
        }
    }
}

// === Utilities ===

std::vector<ActorId> ActorStore::GetAllActiveActors() const {
    std::vector<ActorId> result;
    
    if (!initialized_) {
        return result;
    }
    
    // Add active players
    for (const auto& pair : player_actors_) {
        const PlayerActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            result.push_back(pair.first);
        }
    }
    
    // TODO: Milestone C2 - Add active monsters
    
    return result;
}

std::vector<ActorId> ActorStore::GetAllActivePlayers() const {
    std::vector<ActorId> result;
    
    if (!initialized_) {
        return result;
    }
    
    for (const auto& pair : player_actors_) {
        const PlayerActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            result.push_back(pair.first);
        }
    }
    
    return result;
}

int ActorStore::GetActivePlayerCount() const {
    if (!initialized_) {
        return 0;
    }
    
    int count = 0;
    for (const auto& pair : player_actors_) {
        const PlayerActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            count++;
        }
    }
    
    return count;
}

} // namespace devilution

#endif // ENABLE_GAP