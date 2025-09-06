#pragma once

#ifdef ENABLE_GAP

#include "actor.h"
#include "player_actor.h"
#include <memory>
#include <unordered_map>

namespace devilution {

/**
 * @brief Centralized registry for all Actor instances
 * 
 * ActorStore manages the lifecycle of Actor facades and provides
 * unified lookups across all entity types. This enables GAP
 * and other systems to work with entities uniformly.
 * 
 * Phase 2.1 Milestone C3: Actor Store for unified access
 */
class ActorStore {
public:
    static ActorStore& Instance() {
        static ActorStore instance;
        return instance;
    }
    
    // === Lifecycle Management ===
    void Initialize();
    void Shutdown();
    void Refresh(); // Update actor list based on current game state
    
    // === Unified Lookups ===
    Actor* GetActor(ActorId id);
    const Actor* GetActor(ActorId id) const;
    
    // === Type-Specific Lookups ===
    PlayerActor* GetPlayerActor(int player_index);
    const PlayerActor* GetPlayerActor(int player_index) const;
    
    // TODO: Milestone C2 - Add MonsterActor lookups
    // MonsterActor* GetMonsterActor(int monster_index);
    
    // === Iteration ===
    void ForEachActivePlayer(std::function<void(PlayerActor&)> callback);
    void ForEachActivePlayer(std::function<void(const PlayerActor&)> callback) const;
    
    // TODO: Milestone C2 - Add monster iteration
    // void ForEachActiveMonster(std::function<void(MonsterActor&)> callback);
    
    // === Utilities ===
    std::vector<ActorId> GetAllActiveActors() const;
    std::vector<ActorId> GetAllActivePlayers() const;
    int GetActivePlayerCount() const;
    
    // TODO: Milestone C2
    // std::vector<ActorId> GetAllActiveMonsters() const;
    // int GetActiveMonsterCount() const;
    
private:
    ActorStore() = default;
    ~ActorStore() = default;
    
    // Non-copyable, non-movable singleton
    ActorStore(const ActorStore&) = delete;
    ActorStore& operator=(const ActorStore&) = delete;
    
    // Actor storage
    std::unordered_map<ActorId, std::unique_ptr<PlayerActor>> player_actors_;
    // TODO: Milestone C2
    // std::unordered_map<ActorId, std::unique_ptr<MonsterActor>> monster_actors_;
    
    bool initialized_ = false;
};

} // namespace devilution

#endif // ENABLE_GAP