#!/usr/bin/env python3
"""
Systematic Exploration Algorithm for GAP AI

This module implements frontier-based exploration to ensure complete level coverage.
It uses the exploration data from GAP state to make intelligent pathfinding decisions
and systematically clear dungeon levels.

Key Features:
- Frontier-based exploration (unexplored boundary detection)  
- Level completion tracking
- Priority-based area selection
- Systematic room clearing
- Backtracking for missed areas
"""

import heapq
import math
from typing import Dict, Any, List, Tuple, Optional, Set
import json


class ExplorationManager:
    """Manages systematic exploration of dungeon levels."""
    
    def __init__(self):
        self.level_maps = {}  # level_num -> explored_tiles
        self.visit_counts = {}  # (x, y) -> count
        self.dead_ends = set()  # tiles that lead nowhere
        self.completion_status = {}  # level_num -> completion_percentage
        self.exploration_goals = []  # priority queue of exploration targets
        self.last_progress_time = 0
        self.stuck_in_exploration = 0
        
    def get_exploration_action(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get the next exploration action based on current game state.
        
        Args:
            state: Current GAP state
            
        Returns:
            Intent dict for exploration move or None if exploration complete
        """
        player = state.get('player', {})
        exploration_data = state.get('vision', {}).get('exploration', {})
        current_level = player.get('level', 1)
        player_pos = tuple(player.get('pos', [0, 0]))
        
        # Update our exploration data
        self._update_exploration_data(current_level, exploration_data, player_pos, state.get('timestamp', 0))
        
        # Check if current level exploration is complete
        completion = self._calculate_level_completion(current_level, exploration_data)
        if completion >= 0.95:  # 95% exploration considered complete
            return self._find_stairs_action(exploration_data)
        
        # Find the best frontier tile to explore
        frontiers = exploration_data.get('frontiers', [])
        if not frontiers:
            # No frontiers detected - might be complete or stuck
            return self._handle_no_frontiers(current_level, player_pos, exploration_data)
        
        # Select best frontier based on priority algorithm
        target_frontier = self._select_best_frontier(frontiers, player_pos, current_level)
        
        if target_frontier:
            return {
                "type": "intent",
                "action": "path",  # Use path intent for longer distance navigation
                "params": {"x": target_frontier[0], "y": target_frontier[1]},
                "reasoning": f"Systematic exploration: targeting frontier at {target_frontier}"
            }
        
        return None
    
    def _update_exploration_data(self, level: int, exploration_data: Dict[str, Any], 
                                player_pos: Tuple[int, int], timestamp: int):
        """Update internal exploration tracking."""
        # Track visit counts
        if player_pos not in self.visit_counts:
            self.visit_counts[player_pos] = 0
        self.visit_counts[player_pos] += 1
        
        # Update level completion
        completion = self._calculate_level_completion(level, exploration_data)
        self.completion_status[level] = completion
        
        # Track exploration progress to detect being stuck
        if completion > self.completion_status.get(level, 0):
            self.last_progress_time = timestamp
            self.stuck_in_exploration = 0
        elif timestamp - self.last_progress_time > 30000:  # 30 seconds no progress
            self.stuck_in_exploration += 1
    
    def _calculate_level_completion(self, level: int, exploration_data: Dict[str, Any]) -> float:
        """Calculate exploration completion percentage for current level."""
        # This is a simplified heuristic - real completion would need more data
        # from the game about total explorable area
        
        current_radius = exploration_data.get('exploration_radius', 20)
        frontiers_count = len(exploration_data.get('frontiers', []))
        objects_count = len(exploration_data.get('objects', []))
        
        # Estimate completion based on frontier density and unexplored objects
        # Fewer frontiers = more complete exploration, but objects indicate more to explore
        if frontiers_count == 0:
            # If we have objects to explore, we're not complete yet
            if objects_count > 0:
                return 0.85  # High completion but not done - objects to investigate
            return 1.0  # No frontiers and no objects = complete
        elif frontiers_count < 5:
            return 0.9 + (5 - frontiers_count) * 0.02  # 90-100%
        elif frontiers_count < 20:
            return 0.5 + (20 - frontiers_count) * 0.02  # 50-90%
        else:
            return min(0.5, frontiers_count / 100)  # 0-50%
    
    def _select_best_frontier(self, frontiers: List[List[int]], player_pos: Tuple[int, int], 
                            level: int) -> Optional[Tuple[int, int]]:
        """Select the best frontier tile to explore next."""
        if not frontiers:
            return None
        
        scored_frontiers = []
        px, py = player_pos
        
        for frontier in frontiers:
            fx, fy = frontier[0], frontier[1]
            frontier_tuple = (fx, fy)
            
            # Calculate distance (Euclidean)
            distance = math.sqrt((fx - px) ** 2 + (fy - py) ** 2)
            
            # Base score (closer is better)
            score = 1000 - distance
            
            # Penalty for frequently visited areas
            visit_penalty = self.visit_counts.get(frontier_tuple, 0) * 50
            score -= visit_penalty
            
            # Penalty for known dead ends
            if frontier_tuple in self.dead_ends:
                score -= 200
            
            # Bonus for areas we haven't been to
            if self.visit_counts.get(frontier_tuple, 0) == 0:
                score += 100
            
            # Prefer frontiers in cardinal directions (easier pathfinding)
            if fx == px or fy == py:
                score += 20
            
            scored_frontiers.append((score, distance, frontier_tuple))
        
        # Sort by score (highest first), then by distance (closest first)
        scored_frontiers.sort(key=lambda x: (-x[0], x[1]))
        
        if scored_frontiers:
            return scored_frontiers[0][2]
        
        return None
    
    def _find_stairs_action(self, exploration_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find action to move to stairs when exploration is complete."""
        if exploration_data.get('stairs_visible', False):
            stairs_pos = exploration_data.get('stairs_pos', [])
            stairs_type = exploration_data.get('stairs_type', 'unknown')
            
            if stairs_pos:
                return {
                    "type": "intent",
                    "action": "path",
                    "params": {"x": stairs_pos[0], "y": stairs_pos[1]},
                    "reasoning": f"Level complete ({self.completion_status.get(1, 0):.1%}), heading to {stairs_type} at {stairs_pos}"
                }
        
        return None
    
    def _handle_no_frontiers(self, level: int, player_pos: Tuple[int, int], 
                           exploration_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle case where no frontiers are detected."""
        # Check if stairs are visible - level might be complete
        if exploration_data.get('stairs_visible', False):
            return self._find_stairs_action(exploration_data)
        
        # Look for unexplored objects (chests, barrels, doors)
        objects = exploration_data.get('objects', [])
        # Prioritize doors first, then other objects
        doors = [obj for obj in objects if obj.get('type', '').lower() == 'door']
        other_objects = [obj for obj in objects if obj.get('type', '').lower() != 'door']
        
        # Target doors first as they may unlock new areas
        for obj in doors + other_objects:
            obj_pos = obj.get('pos', [])
            if obj_pos:
                return {
                    "type": "intent",
                    "action": "path",
                    "params": {"x": obj_pos[0], "y": obj_pos[1]},
                    "reasoning": f"No frontiers found, investigating {obj.get('type', 'object')} at {obj_pos}"
                }
        
        # If stuck, try a different exploration pattern
        if self.stuck_in_exploration > 3:
            return self._generate_unstuck_action(player_pos)
        
        return None
    
    def _generate_unstuck_action(self, player_pos: Tuple[int, int]) -> Dict[str, Any]:
        """Generate action to get unstuck from exploration loop."""
        # Try moving to a less visited area
        least_visited = min(self.visit_counts.items(), key=lambda x: x[1], default=(player_pos, 0))
        target_pos = least_visited[0]
        
        # If we're already at the least visited spot, try a random direction
        if target_pos == player_pos:
            px, py = player_pos
            # Try moving in a spiral pattern outward
            for radius in range(5, 20, 5):
                target_pos = (px + radius, py)  # Try east first
                break
        
        return {
            "type": "intent",
            "action": "path",
            "params": {"x": target_pos[0], "y": target_pos[1]},
            "reasoning": f"Unstuck maneuver: exploring less visited area at {target_pos}"
        }
    
    def get_exploration_status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Get current exploration status for debugging/logging."""
        player = state.get('player', {})
        exploration_data = state.get('vision', {}).get('exploration', {})
        current_level = player.get('level', 1)
        
        completion = self._calculate_level_completion(current_level, exploration_data)
        frontiers_count = len(exploration_data.get('frontiers', []))
        
        return {
            'current_level': current_level,
            'completion_percentage': completion,
            'frontiers_available': frontiers_count,
            'stairs_visible': exploration_data.get('stairs_visible', False),
            'objects_available': len(exploration_data.get('objects', [])),
            'visit_count_current_pos': self.visit_counts.get(tuple(player.get('pos', [0, 0])), 0),
            'total_positions_visited': len(self.visit_counts),
            'stuck_counter': self.stuck_in_exploration,
            'dead_ends_known': len(self.dead_ends)
        }


# Standalone exploration algorithm implementation
def systematic_exploration_step(state: Dict[str, Any], memory: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Standalone function for systematic exploration - can be integrated into any agent.
    
    Args:
        state: Current GAP game state
        memory: Optional memory dict to maintain exploration state between calls
        
    Returns:
        Dict with 'action' (intent dict) and 'memory' (updated memory state)
    """
    if memory is None:
        memory = {'exploration_manager': ExplorationManager()}
    
    if 'exploration_manager' not in memory:
        memory['exploration_manager'] = ExplorationManager()
    
    exploration_manager = memory['exploration_manager']
    action = exploration_manager.get_exploration_action(state)
    status = exploration_manager.get_exploration_status(state)
    
    return {
        'action': action,
        'memory': memory,
        'status': status
    }


# Example usage and testing
if __name__ == "__main__":
    # Test the exploration system
    explorer = ExplorationManager()
    
    # Test basic exploration scenario
    test_state = {
        'timestamp': 1000,
        'player': {'level': 1, 'pos': [25, 25]},
        'vision': {
            'exploration': {
                'current_level': 1,
                'exploration_radius': 10,
                'stairs_visible': False,
                'objects': [
                    {'type': 'chest', 'pos': [30, 30]},
                    {'type': 'barrel', 'pos': [20, 35]}
                ],
                'frontiers': [
                    [35, 25], [25, 35], [15, 25], [25, 15]
                ]
            }
        }
    }
    
    action = explorer.get_exploration_action(test_state)
    print("Exploration action:", json.dumps(action, indent=2))
    
    status = explorer.get_exploration_status(test_state)
    print("Exploration status:", json.dumps(status, indent=2))
    
    # Test level completion scenario
    complete_state = {
        'timestamp': 2000,
        'player': {'level': 1, 'pos': [50, 50]},
        'vision': {
            'exploration': {
                'current_level': 1,
                'exploration_radius': 15,
                'stairs_visible': True,
                'stairs_pos': [60, 60],
                'stairs_type': 'down_next',
                'objects': [],
                'frontiers': []  # No frontiers = exploration complete
            }
        }
    }
    
    action = explorer.get_exploration_action(complete_state)
    print("Level complete action:", json.dumps(action, indent=2))
    
    # Test standalone function
    result = systematic_exploration_step(test_state)
    print("Standalone result:", json.dumps({
        'action': result['action'],
        'status': result['status']
    }, indent=2))