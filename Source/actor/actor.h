#pragma once

#ifdef ENABLE_GAP

#include <cstdint>
#include <string>
#include "../engine/point.hpp"

namespace devilution {

// Forward declarations
struct Item;
enum class SpellID : int8_t;

/**
 * @brief Unique identifier for actors across all types
 * 
 * ActorId encodes both the type and index to allow unified lookups:
 * - Players: 0x10000000 | player_index (0-3)
 * - Monsters: 0x20000000 | monster_index 
 * 
 * This ensures no ID collisions between entity types.
 */
using ActorId = uint32_t;

// ActorId constants
namespace ActorIds {
    constexpr ActorId INVALID = 0;
    constexpr ActorId PLAYER_BASE = 0x10000000;
    constexpr ActorId MONSTER_BASE = 0x20000000;
    
    inline bool IsPlayer(ActorId id) { return (id & 0xF0000000) == PLAYER_BASE; }
    inline bool IsMonster(ActorId id) { return (id & 0xF0000000) == MONSTER_BASE; }
    inline int GetPlayerIndex(ActorId id) { return static_cast<int>(id & 0x0FFFFFFF); }
    inline int GetMonsterIndex(ActorId id) { return static_cast<int>(id & 0x0FFFFFFF); }
    
    inline ActorId ForPlayer(int index) { return PLAYER_BASE | static_cast<uint32_t>(index); }
    inline ActorId ForMonster(int index) { return MONSTER_BASE | static_cast<uint32_t>(index); }
}

/**
 * @brief Base interface for all controllable entities in the game
 * 
 * Actor provides a unified interface over Players and Monsters, enabling:
 * - Common GAP state extraction
 * - Unified command dispatch 
 * - Shared AI and utility functions
 * - Future expansion to other entity types
 * 
 * This is a thin façade over existing Player/Monster structs - no behavior changes.
 */
class Actor {
public:
    virtual ~Actor() = default;
    
    // === Core Identity ===
    virtual ActorId GetId() const = 0;
    virtual const char* GetName() const = 0;
    virtual const char* GetTypeName() const = 0;
    
    // === Spatial Properties ===
    virtual Point GetPosition() const = 0;
    virtual Point GetFuturePosition() const = 0; // Where actor will be after current animation
    virtual int GetLevel() const = 0; // Dungeon level
    
    // === Health & Status ===
    virtual int GetHitPoints() const = 0;
    virtual int GetMaxHitPoints() const = 0;
    virtual bool IsAlive() const = 0;
    virtual bool IsActive() const = 0; // Present in game world
    
    // === Combat Properties ===
    virtual int GetArmorClass() const = 0;
    virtual bool IsPlayerMinion() const = 0; // For monsters - is this controlled by a player?
    
    // === Command Interface (Milestone C1: Players only) ===
    virtual bool CanReceiveCommands() const = 0; // Only true for Players initially
    virtual void MoveTo(Point target) = 0;
    virtual void AttackTarget(ActorId target) = 0;
    virtual void AttackPosition(Point target) = 0;
    virtual void InteractWithObject(int object_id) = 0;
    
    // === Utility ===
    virtual int DistanceTo(const Actor& other) const;
    virtual int DistanceTo(Point target) const;
};

} // namespace devilution

#endif // ENABLE_GAP