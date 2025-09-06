#pragma once

#ifdef ENABLE_GAP

#include "actor.h"
#include "../monster.h"

namespace devilution {

/**
 * @brief Actor façade over Monster struct
 * 
 * MonsterActor provides the unified Actor interface for monsters, primarily
 * to create consistent state publishing for GAP. This abstracts away the
 * game's non-ECS architecture where monster data is scattered across
 * multiple arrays and requires manual field extraction.
 * 
 * WHY THIS EXISTS:
 * The core game doesn't use an ECS - monster state is spread across:
 * - Monsters[] array with complex indexing via ActiveMonsters[]  
 * - Fixed-point math requiring manual conversion
 * - Inconsistent field naming vs Player structs
 * - Manual iteration patterns throughout GAP state extraction
 * 
 * MonsterActor centralizes this complexity and provides a clean interface
 * that matches PlayerActor, enabling consistent state publishing patterns.
 * 
 * Phase 3 Milestone C2: Read-only monster access for state extraction
 */
class MonsterActor : public Actor {
private:
    int monster_index_;
    Monster* monster_;
    
public:
    explicit MonsterActor(int monster_index);
    
    // Validate monster is still active (important as monsters die/spawn)
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
    
    // Command interface - monsters are read-only for GAP
    bool CanReceiveCommands() const override;
    void MoveTo(Point target) override;
    void AttackTarget(ActorId target) override;
    void AttackPosition(Point target) override;
    void InteractWithObject(int object_id) override;
    
    // Monster-specific accessors
    Monster* GetMonster() const { return monster_; }
    int GetMonsterIndex() const { return monster_index_; }
    
    // Extended properties for GAP state extraction
    int GetHitPointsPercent() const;
    bool IsUnique() const;
    int GetResistance(int damage_type) const; // For future tactical analysis
    
    // State publishing helpers
    std::string GetDisplayName() const; // Truncated name for JSON
    bool IsInRange(Point target, int max_distance) const;
};

} // namespace devilution

#endif // ENABLE_GAP