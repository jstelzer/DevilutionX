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
    monster_actors_.clear();
    
    initialized_ = false;
}

void ActorStore::Refresh() {
    if (!initialized_) {
        return;
    }
    
    // Note: PlayerActor instances validate themselves via IsValid()
    // So no refresh needed for players.
    
    // Milestone C2: Refresh monster actors based on ActiveMonsters
    // Clear existing monster actors 
    monster_actors_.clear();
    
    // Create MonsterActor instances for all active monsters
    for (size_t i = 0; i < ActiveMonsterCount; i++) {
        int monster_index = ActiveMonsters[i];
        if (monster_index >= 0 && static_cast<size_t>(monster_index) < MaxMonsters) {
            ActorId id = ActorIds::ForMonster(monster_index);
            monster_actors_[id] = std::make_unique<MonsterActor>(monster_index);
        }
    }
    
    // Debug logging
    if (ActiveMonsterCount > 0) {
        std::cout << "ActorStore: Refreshed " << ActiveMonsterCount << " monster actors" << std::endl;
    }
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
    
    // Milestone C2: Monster lookup
    if (ActorIds::IsMonster(id)) {
        auto it = monster_actors_.find(id);
        return (it != monster_actors_.end()) ? it->second.get() : nullptr;
    }
    
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

MonsterActor* ActorStore::GetMonsterActor(int monster_index) {
    if (!initialized_ || monster_index < 0 || static_cast<size_t>(monster_index) >= MaxMonsters) {
        return nullptr;
    }
    
    ActorId id = ActorIds::ForMonster(monster_index);
    auto it = monster_actors_.find(id);
    return (it != monster_actors_.end()) ? it->second.get() : nullptr;
}

const MonsterActor* ActorStore::GetMonsterActor(int monster_index) const {
    return const_cast<ActorStore*>(this)->GetMonsterActor(monster_index);
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

void ActorStore::ForEachActiveMonster(std::function<void(MonsterActor&)> callback) {
    if (!initialized_ || !callback) {
        return;
    }
    
    for (auto& pair : monster_actors_) {
        MonsterActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            callback(*actor);
        }
    }
}

void ActorStore::ForEachActiveMonster(std::function<void(const MonsterActor&)> callback) const {
    if (!initialized_ || !callback) {
        return;
    }
    
    for (const auto& pair : monster_actors_) {
        const MonsterActor* actor = pair.second.get();
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
    
    // Milestone C2: Add active monsters
    for (const auto& pair : monster_actors_) {
        const MonsterActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            result.push_back(pair.first);
        }
    }
    
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

std::vector<ActorId> ActorStore::GetAllActiveMonsters() const {
    std::vector<ActorId> result;
    
    if (!initialized_) {
        return result;
    }
    
    for (const auto& pair : monster_actors_) {
        const MonsterActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            result.push_back(pair.first);
        }
    }
    
    return result;
}

int ActorStore::GetActiveMonsterCount() const {
    if (!initialized_) {
        return 0;
    }
    
    int count = 0;
    for (const auto& pair : monster_actors_) {
        const MonsterActor* actor = pair.second.get();
        if (actor && actor->IsValid()) {
            count++;
        }
    }
    
    return count;
}

} // namespace devilution

#endif // ENABLE_GAP