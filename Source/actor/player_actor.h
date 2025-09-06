#pragma once

#ifdef ENABLE_GAP

#include "actor.h"
#include "../player.h"

namespace devilution {

/**
 * @brief Actor façade over Player struct
 * 
 * PlayerActor provides the unified Actor interface while delegating
 * all operations to the underlying Player struct. This maintains
 * complete compatibility with existing code.
 * 
 * Phase 2.1 Milestone C1: Players only - no behavior changes
 */
class PlayerActor : public Actor {
private:
    int player_index_;
    Player* player_;
    
public:
    explicit PlayerActor(int player_index);
    
    // Validate player is still active (important for multiplayer)
    bool IsValid() const;
    
    // Actor interface implementation
    ActorId GetId() const override;
    const char* GetName() const override;
    const char* GetTypeName() const override;
    
    Point GetPosition() const override;
    Point GetFuturePosition() const override;
    int GetLevel() const override;
    
    int GetHitPoints() const override;
    int GetMaxHitPoints() const override;
    bool IsAlive() const override;
    bool IsActive() const override;
    
    int GetArmorClass() const override;
    bool IsPlayerMinion() const override;
    
    // Command interface - routes to existing game systems
    bool CanReceiveCommands() const override;
    void MoveTo(Point target) override;
    void AttackTarget(ActorId target) override;
    void AttackPosition(Point target) override;
    void InteractWithObject(int object_id) override;
    
    // Player-specific accessors
    Player* GetPlayer() const { return player_; }
    int GetPlayerIndex() const { return player_index_; }
    bool IsCompanion() const { return player_index_ != MyPlayerId; }
    
    // Extended properties for GAP state extraction
    int GetMana() const;
    int GetMaxMana() const;
    bool IsInTown() const;
    const Item* GetBeltItem(int slot) const;
};

} // namespace devilution

#endif // ENABLE_GAP