#ifdef ENABLE_GAP

#include "monster_actor.h"
#include "../diablo.h"
#include "../levels/gendung.h"
#include <cmath>
#include <algorithm>
#include <iostream>

namespace devilution {

MonsterActor::MonsterActor(int monster_index) 
    : monster_index_(monster_index), monster_(nullptr) {
    // Validate monster index and get monster pointer
    if (monster_index >= 0 && static_cast<size_t>(monster_index) < MaxMonsters) {
        monster_ = &Monsters[monster_index];
    }
}

bool MonsterActor::IsValid() const {
    // Monster is valid if:
    // 1. We have a valid monster pointer
    // 2. Index is in valid range  
    // 3. Monster is in the active monsters list
    if (!monster_ || monster_index_ < 0 || static_cast<size_t>(monster_index_) >= MaxMonsters) {
        return false;
    }
    
    // Check if monster is in ActiveMonsters list (the game's way of tracking active monsters)
    for (size_t i = 0; i < ActiveMonsterCount; i++) {
        if (ActiveMonsters[i] == static_cast<unsigned>(monster_index_)) {
            return true;
        }
    }
    
    return false;
}

// === Actor Interface Implementation ===

ActorId MonsterActor::GetId() const {
    return ActorIds::ForMonster(monster_index_);
}

const char* MonsterActor::GetName() const {
    if (!IsValid()) return "";
    // Cache the name as a string since monster_->name() returns string_view
    name_cache_ = std::string(monster_->name());
    return name_cache_.c_str();
}

const char* MonsterActor::GetTypeName() const {
    return "Monster";
}

Point MonsterActor::GetPosition() const {
    if (!IsValid()) return {0, 0};
    return monster_->position.tile;
}

Point MonsterActor::GetFuturePosition() const {
    if (!IsValid()) return {0, 0};
    return monster_->position.future;
}

int MonsterActor::GetLevel() const {
    if (!IsValid()) return 0;
    // Monsters don't have a plrlevel equivalent, use current dungeon level
    return static_cast<int>(currlevel);
}

int MonsterActor::GetHitPoints() const {
    if (!IsValid()) return 0;
    return std::max(0, monster_->hitPoints); // Ensure non-negative
}

int MonsterActor::GetMaxHitPoints() const {
    if (!IsValid()) return 0;
    return std::max(1, monster_->maxHitPoints); // Ensure positive for percentage calculations
}

bool MonsterActor::IsAlive() const {
    return IsValid() && monster_->hitPoints > 0;
}

bool MonsterActor::IsActive() const {
    return IsValid(); // For monsters, valid == active (in ActiveMonsters list)
}

int MonsterActor::GetArmorClass() const {
    if (!IsValid()) return 0;
    return monster_->armorClass;
}

bool MonsterActor::IsPlayerMinion() const {
    if (!IsValid()) return false;
    return monster_->isPlayerMinion();
}

// === Command Interface (Read-Only) ===

bool MonsterActor::CanReceiveCommands() const {
    return false; // Milestone C2: Monsters are read-only for GAP
}

void MonsterActor::MoveTo(Point target) {
    // No-op: Monsters not controllable in current phase
    std::cerr << "MonsterActor: MoveTo called but monsters are read-only" << std::endl;
}

void MonsterActor::AttackTarget(ActorId target) {
    // No-op: Monsters not controllable in current phase  
    std::cerr << "MonsterActor: AttackTarget called but monsters are read-only" << std::endl;
}

void MonsterActor::AttackPosition(Point target) {
    // No-op: Monsters not controllable in current phase
    std::cerr << "MonsterActor: AttackPosition called but monsters are read-only" << std::endl;
}

void MonsterActor::InteractWithObject(int object_id) {
    // No-op: Monsters not controllable in current phase
    std::cerr << "MonsterActor: InteractWithObject called but monsters are read-only" << std::endl;
}

// === Monster-Specific Extensions ===

int MonsterActor::GetHitPointsPercent() const {
    if (!IsValid()) return 0;
    
    int max_hp = GetMaxHitPoints();
    if (max_hp <= 0) return 0;
    
    return (GetHitPoints() * 100) / max_hp;
}

bool MonsterActor::IsUnique() const {
    if (!IsValid()) return false;
    // Check if this is a unique monster (boss, special enemy, etc.)
    // This is a simplified check - could be expanded based on monster type flags
    return monster_->uniqueType != UniqueMonsterType::None;
}

int MonsterActor::GetResistance(int damage_type) const {
    if (!IsValid()) return 0;
    // Placeholder for future tactical analysis
    // Would need to access monster type resistance data
    return 0;
}

// === State Publishing Helpers ===

std::string MonsterActor::GetDisplayName() const {
    if (!IsValid()) return "";
    
    std::string name(GetName());
    
    // Truncate long names for JSON compactness (same logic as gap_state.cpp)
    if (name.length() > 20) {
        name = name.substr(0, 20);
    }
    
    return name;
}

bool MonsterActor::IsInRange(Point target, int max_distance) const {
    if (!IsValid()) return false;
    
    Point pos = GetPosition();
    int distance = DistanceTo(target);
    
    return distance <= max_distance;
}

} // namespace devilution

#endif // ENABLE_GAP