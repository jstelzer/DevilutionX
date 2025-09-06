#!/usr/bin/env python3
"""
Survival Reflex System for GAP AI

This module provides critical survival logic that overrides LLM decisions
when the AI is in immediate danger. It implements fast, deterministic
responses to life-threatening situations.

Key Features:
- Emergency healing when HP is critically low
- Pre-emptive healing under heavy fire
- Cooldown management for potion usage
- Kiting behavior when overwhelmed
- Resource conservation strategies
"""

import time
from typing import Dict, Any, Optional, List
import json


class SurvivalReflexes:
    """Critical survival logic that overrides LLM decisions when in danger."""
    
    def __init__(self):
        self.last_potion_time = 0
        self.potion_cooldown = 500  # ms - matches Diablo's potion cooldown
        self.emergency_hp_threshold = 0.15  # COMBAT: More aggressive - 15% HP for emergency
        self.preemptive_hp_threshold = 0.35  # COMBAT: More aggressive - 35% HP for pre-emptive healing  
        self.overwhelming_enemy_count = 6  # COMBAT: More aggressive - 6+ enemies = overwhelming (was 4)
        self.min_kiting_distance = 3  # minimum tiles away from enemies
        
        # Track recent actions for smarter decision making
        self.recent_potions_used = []
        self.last_enemy_positions = {}
        self.last_player_position = None
        self.stuck_counter = 0
        
    def check_emergency_actions(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check for emergency situations and return immediate action if needed.
        
        This method is called before LLM decision-making and can override
        LLM choices when survival is at stake.
        
        Args:
            state: Current game state from GAP
            
        Returns:
            Emergency intent dict if action needed, None otherwise
        """
        current_time = state.get('timestamp', 0)
        player = state.get('player', {})
        monsters = state.get('monsters', [])
        
        # Update tracking data
        self._update_tracking_data(player, monsters, current_time)
        
        # Emergency healing - highest priority
        heal_action = self._check_emergency_healing(player, monsters, current_time)
        if heal_action:
            return heal_action
        
        # Kiting behavior when overwhelmed
        kite_action = self._check_kiting_behavior(player, monsters)
        if kite_action:
            return kite_action
        
        # Pre-emptive healing under sustained fire
        preemptive_action = self._check_preemptive_healing(player, monsters, current_time)
        if preemptive_action:
            return preemptive_action
            
        return None
    
    def _check_emergency_healing(self, player: Dict[str, Any], monsters: List[Dict[str, Any]], 
                                current_time: int) -> Optional[Dict[str, Any]]:
        """Check if emergency healing is needed."""
        hp_ratio = player.get('hp', 0) / max(player.get('hp_max', 1), 1)
        
        if hp_ratio < self.emergency_hp_threshold:
            if self._can_use_potion(current_time):
                self.last_potion_time = current_time
                return {
                    "type": "intent",
                    "action": "use_potion", 
                    "params": {"kind": "hp"},
                    "reasoning": f"EMERGENCY: HP at {hp_ratio:.1%}, using health potion"
                }
        
        return None
    
    def _check_preemptive_healing(self, player: Dict[str, Any], monsters: List[Dict[str, Any]], 
                                 current_time: int) -> Optional[Dict[str, Any]]:
        """Check if pre-emptive healing is needed before taking more damage."""
        if not monsters:  # No threats nearby
            return None
            
        hp_ratio = player.get('hp', 0) / max(player.get('hp_max', 1), 1)
        
        # Only consider pre-emptive healing if we're at moderate health
        if hp_ratio > self.preemptive_hp_threshold:
            return None
        
        # Estimate incoming damage per second
        incoming_dps = self._estimate_incoming_damage(monsters)
        if incoming_dps <= 0:
            return None
        
        # If we're likely to die within 1.5 seconds, heal now
        current_hp = player.get('hp', 0)
        time_to_death = current_hp / incoming_dps if incoming_dps > 0 else float('inf')
        
        if time_to_death < 1.5 and self._can_use_potion(current_time):
            self.last_potion_time = current_time
            return {
                "type": "intent",
                "action": "use_potion",
                "params": {"kind": "hp"},
                "reasoning": f"PRE-EMPTIVE: Estimated {time_to_death:.1f}s to death, healing now"
            }
        
        return None
    
    def _check_kiting_behavior(self, player: Dict[str, Any], monsters: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Check if we need to kite away from overwhelming enemies."""
        if len(monsters) < self.overwhelming_enemy_count:
            return None
        
        player_pos = player.get('pos', [0, 0])
        
        # Find the safest direction (away from most enemies)
        safe_direction = self._find_safest_direction(player_pos, monsters)
        if safe_direction:
            target_x = player_pos[0] + safe_direction[0] * self.min_kiting_distance
            target_y = player_pos[1] + safe_direction[1] * self.min_kiting_distance
            
            return {
                "type": "intent",
                "action": "move",
                "params": {"x": target_x, "y": target_y},
                "reasoning": f"KITING: {len(monsters)} enemies overwhelming, retreating to safe distance"
            }
        
        return None
    
    def _estimate_incoming_damage(self, monsters: List[Dict[str, Any]]) -> float:
        """Estimate damage per second from nearby monsters."""
        total_dps = 0
        
        for monster in monsters:
            distance = monster.get('distance', 999)
            if distance <= 5:  # Only count monsters in combat range
                # Simple heuristic: closer monsters = more dangerous
                # This is a rough estimate - real DPS would require monster data
                base_dps = 20  # base damage per second estimate
                distance_multiplier = max(0.2, (6 - distance) / 5)  # closer = more dangerous
                hp_multiplier = monster.get('hp_percent', 100) / 100  # wounded monsters less dangerous
                
                monster_dps = base_dps * distance_multiplier * hp_multiplier
                total_dps += monster_dps
        
        return total_dps
    
    def _find_safest_direction(self, player_pos: List[int], monsters: List[Dict[str, Any]]) -> Optional[List[int]]:
        """Find the direction with fewest nearby enemies."""
        directions = [
            [-1, -1], [-1, 0], [-1, 1],  # northwest, west, southwest
            [0, -1],           [0, 1],   # north, south
            [1, -1],  [1, 0],  [1, 1]    # northeast, east, southeast
        ]
        
        best_direction = None
        min_threat_score = float('inf')
        
        for direction in directions:
            threat_score = 0
            test_pos = [player_pos[0] + direction[0] * 3, player_pos[1] + direction[1] * 3]
            
            for monster in monsters:
                monster_pos = monster.get('pos', [999, 999])
                # Calculate distance from test position to monster
                dx = abs(test_pos[0] - monster_pos[0])
                dy = abs(test_pos[1] - monster_pos[1])
                distance = max(dx, dy)  # Chebyshev distance
                
                if distance < 5:  # Monster would still be close
                    threat_score += (5 - distance) * 10  # Closer = higher threat
            
            if threat_score < min_threat_score:
                min_threat_score = threat_score
                best_direction = direction
        
        return best_direction if min_threat_score < float('inf') else None
    
    def _can_use_potion(self, current_time: int) -> bool:
        """Check if enough time has passed since last potion use."""
        return (current_time - self.last_potion_time) >= self.potion_cooldown
    
    def _update_tracking_data(self, player: Dict[str, Any], monsters: List[Dict[str, Any]], current_time: int):
        """Update internal tracking data for smarter decisions."""
        # Track player position for stuck detection
        current_pos = tuple(player.get('pos', [0, 0]))
        if self.last_player_position == current_pos:
            self.stuck_counter += 1
        else:
            self.stuck_counter = 0
        self.last_player_position = current_pos
        
        # Track enemy positions for movement prediction
        for monster in monsters:
            monster_id = monster.get('id', -1)
            monster_pos = tuple(monster.get('pos', [0, 0]))
            self.last_enemy_positions[monster_id] = monster_pos
        
        # Clean up old potion usage records (keep last 10 seconds)
        cutoff_time = current_time - 10000  # 10 seconds ago
        self.recent_potions_used = [
            usage_time for usage_time in self.recent_potions_used 
            if usage_time > cutoff_time
        ]
    
    def get_survival_status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Get current survival assessment for debugging/logging."""
        player = state.get('player', {})
        monsters = state.get('monsters', [])
        current_time = state.get('timestamp', 0)
        
        hp_ratio = player.get('hp', 0) / max(player.get('hp_max', 1), 1)
        incoming_dps = self._estimate_incoming_damage(monsters)
        time_to_death = player.get('hp', 0) / incoming_dps if incoming_dps > 0 else float('inf')
        
        return {
            'hp_ratio': hp_ratio,
            'emergency_threshold': self.emergency_hp_threshold,
            'preemptive_threshold': self.preemptive_hp_threshold,
            'enemy_count': len(monsters),
            'incoming_dps': incoming_dps,
            'time_to_death': time_to_death,
            'can_use_potion': self._can_use_potion(current_time),
            'time_since_last_potion': current_time - self.last_potion_time,
            'stuck_counter': self.stuck_counter
        }


# Example usage and testing
if __name__ == "__main__":
    # Test the survival reflex system
    reflexes = SurvivalReflexes()
    
    # Test emergency healing scenario
    critical_state = {
        'timestamp': 1000,
        'player': {'hp': 20, 'hp_max': 100, 'pos': [50, 50]},  # 20% HP - below 25% threshold
        'monsters': [
            {'id': 1, 'pos': [52, 52], 'distance': 2, 'hp_percent': 80}
        ]
    }
    
    action = reflexes.check_emergency_actions(critical_state)
    print("Emergency test:", json.dumps(action, indent=2))
    
    # Test overwhelming enemies scenario
    overwhelming_state = {
        'timestamp': 2000,
        'player': {'hp': 60, 'hp_max': 100, 'pos': [50, 50]},
        'monsters': [
            {'id': 1, 'pos': [51, 51], 'distance': 1, 'hp_percent': 100},
            {'id': 2, 'pos': [49, 51], 'distance': 1, 'hp_percent': 90},
            {'id': 3, 'pos': [51, 49], 'distance': 1, 'hp_percent': 85},
            {'id': 4, 'pos': [49, 49], 'distance': 1, 'hp_percent': 95},
            {'id': 5, 'pos': [52, 50], 'distance': 2, 'hp_percent': 70}
        ]
    }
    
    action = reflexes.check_emergency_actions(overwhelming_state)
    print("Overwhelming test:", json.dumps(action, indent=2))
    
    # Test survival status
    status = reflexes.get_survival_status(critical_state)
    print("Survival status:", json.dumps(status, indent=2))