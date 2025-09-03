#!/usr/bin/env python3
"""
Robust Navigation System for GAP AI

This module implements A* pathfinding with waypoint chunking to solve complex
navigation problems. It breaks long paths into manageable segments and provides
obstacle avoidance with stuck detection.

Key Features:
- A* pathfinding algorithm 
- Waypoint chunking (3-5 tile segments)
- Obstacle detection and avoidance
- Stuck detection and recovery
- Dynamic path recalculation
- Door/interaction handling
"""

import heapq
import math
from typing import Dict, Any, List, Tuple, Optional, Set
import json


class NavigationPlanner:
    """Advanced pathfinding with A* algorithm and waypoint management."""
    
    def __init__(self):
        self.blocked_edges = {}  # cache blocked paths temporarily  
        self.stuck_counter = 0
        self.last_position = None
        self.current_path = []
        self.current_waypoint_index = 0
        self.path_recalc_needed = False
        self.waypoint_chunk_size = 4  # tiles per waypoint
        self.max_pathfinding_distance = 50  # max tiles for pathfinding
        
    def plan_route(self, current_pos: Tuple[int, int], target_pos: Tuple[int, int], 
                   walkable_grid: List[List[bool]], light_radius: int) -> Optional[Dict[str, Any]]:
        """
        Plan a route from current position to target using A* pathfinding.
        
        Args:
            current_pos: Current player position (x, y)
            target_pos: Target destination (x, y)
            walkable_grid: 2D grid of walkable tiles
            light_radius: Player's vision radius
            
        Returns:
            Intent dict for next move or None if path blocked
        """
        # Handle stuck detection
        if self._is_stuck(current_pos):
            return self._handle_stuck_situation(current_pos, walkable_grid, light_radius)
        
        # Check if we need to recalculate path
        if self._need_path_recalculation(current_pos, target_pos):
            self.current_path = self._astar_pathfind(current_pos, target_pos, walkable_grid, light_radius)
            self.current_waypoint_index = 0
            self.path_recalc_needed = False
        
        # Get next waypoint from current path
        next_waypoint = self._get_next_waypoint(current_pos)
        if next_waypoint:
            return {
                "type": "intent",
                "action": "move",
                "params": {"x": next_waypoint[0], "y": next_waypoint[1]},
                "reasoning": f"Navigation: moving to waypoint {next_waypoint} (step {self.current_waypoint_index + 1}/{len(self.current_path)})"
            }
        
        # No valid path found
        return self._handle_no_path(current_pos, target_pos, walkable_grid, light_radius)
    
    def _astar_pathfind(self, start: Tuple[int, int], goal: Tuple[int, int], 
                       walkable_grid: List[List[bool]], light_radius: int) -> List[Tuple[int, int]]:
        """
        A* pathfinding algorithm implementation.
        
        Returns:
            List of waypoint positions from start to goal
        """
        if not walkable_grid:
            return []
        
        grid_height = len(walkable_grid)
        grid_width = len(walkable_grid[0]) if grid_height > 0 else 0
        
        # Convert world coordinates to grid coordinates 
        # Assume walkable_grid is centered on player position
        center_x, center_y = start
        
        def world_to_grid(world_pos):
            wx, wy = world_pos
            gx = (wx - center_x) + light_radius
            gy = (wy - center_y) + light_radius  
            return gx, gy
        
        def grid_to_world(grid_pos):
            gx, gy = grid_pos
            wx = (gx - light_radius) + center_x
            wy = (gy - light_radius) + center_y
            return wx, wy
        
        def is_valid_grid_pos(gx, gy):
            return 0 <= gx < grid_width and 0 <= gy < grid_height and walkable_grid[gy][gx]
        
        start_grid = world_to_grid(start)
        goal_grid = world_to_grid(goal)
        
        if not is_valid_grid_pos(*start_grid) or not is_valid_grid_pos(*goal_grid):
            return []
        
        # A* algorithm
        open_set = [(0, start_grid)]
        came_from = {}
        g_score = {start_grid: 0}
        f_score = {start_grid: self._heuristic(start_grid, goal_grid)}
        
        while open_set:
            current_f, current = heapq.heappop(open_set)
            
            if current == goal_grid:
                # Reconstruct path
                path = []
                while current in came_from:
                    path.append(grid_to_world(current))
                    current = came_from[current]
                path.append(start)
                return self._chunk_path(path[::-1])
            
            # Check neighbors (8-directional movement)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    
                    neighbor = (current[0] + dx, current[1] + dy)
                    
                    if not is_valid_grid_pos(*neighbor):
                        continue
                    
                    # Movement cost (diagonal costs more)
                    move_cost = math.sqrt(dx*dx + dy*dy)
                    tentative_g = g_score[current] + move_cost
                    
                    if neighbor not in g_score or tentative_g < g_score[neighbor]:
                        came_from[neighbor] = current
                        g_score[neighbor] = tentative_g
                        f_score[neighbor] = tentative_g + self._heuristic(neighbor, goal_grid)
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
        
        return []  # No path found
    
    def _chunk_path(self, path: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Break path into waypoint chunks to prevent long movements."""
        if len(path) <= 2:
            return path
        
        chunked = [path[0]]  # Always include start
        current_index = 0
        
        while current_index < len(path) - 1:
            next_index = min(current_index + self.waypoint_chunk_size, len(path) - 1)
            chunked.append(path[next_index])
            current_index = next_index
        
        return chunked
    
    def _heuristic(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Euclidean distance heuristic for A*."""
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        return math.sqrt(dx * dx + dy * dy)
    
    def _is_stuck(self, current_pos: Tuple[int, int]) -> bool:
        """Detect if AI is stuck in the same position."""
        if self.last_position == current_pos:
            self.stuck_counter += 1
            return self.stuck_counter > 5  # Consider stuck after 5+ identical positions
        else:
            self.stuck_counter = 0
            self.last_position = current_pos
            return False
    
    def _need_path_recalculation(self, current_pos: Tuple[int, int], target_pos: Tuple[int, int]) -> bool:
        """Check if path needs to be recalculated."""
        if not self.current_path:
            return True
        
        if self.path_recalc_needed:
            return True
        
        # If we've deviated significantly from the path, recalculate
        if self.current_waypoint_index < len(self.current_path):
            next_waypoint = self.current_path[self.current_waypoint_index]
            distance_to_waypoint = self._distance(current_pos, next_waypoint)
            if distance_to_waypoint > 5:  # Deviated more than 5 tiles
                return True
        
        return False
    
    def _get_next_waypoint(self, current_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Get the next waypoint in the current path."""
        if not self.current_path:
            return None
        
        # Check if we've reached the current waypoint
        if self.current_waypoint_index < len(self.current_path):
            waypoint = self.current_path[self.current_waypoint_index]
            distance = self._distance(current_pos, waypoint)
            
            if distance <= 1.5:  # Close enough to waypoint
                self.current_waypoint_index += 1
                
                # Get next waypoint if available
                if self.current_waypoint_index < len(self.current_path):
                    return self.current_path[self.current_waypoint_index]
            else:
                return waypoint
        
        return None
    
    def _distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Calculate Euclidean distance between positions."""
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        return math.sqrt(dx * dx + dy * dy)
    
    def _handle_stuck_situation(self, current_pos: Tuple[int, int], walkable_grid: List[List[bool]], 
                               light_radius: int) -> Optional[Dict[str, Any]]:
        """Handle stuck situation by finding alternative route."""
        # Try perpendicular movement first
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # cardinal directions
        
        for dx, dy in directions:
            test_pos = (current_pos[0] + dx * 2, current_pos[1] + dy * 2)
            if self._is_position_walkable(test_pos, current_pos, walkable_grid, light_radius):
                self.stuck_counter = 0  # Reset stuck counter
                self.path_recalc_needed = True  # Force path recalculation
                return {
                    "type": "intent",
                    "action": "move",
                    "params": {"x": test_pos[0], "y": test_pos[1]},
                    "reasoning": f"Unstuck maneuver: trying alternative route to {test_pos}"
                }
        
        # If no cardinal direction works, try diagonal
        diagonal_directions = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        for dx, dy in diagonal_directions:
            test_pos = (current_pos[0] + dx * 2, current_pos[1] + dy * 2)
            if self._is_position_walkable(test_pos, current_pos, walkable_grid, light_radius):
                self.stuck_counter = 0
                self.path_recalc_needed = True
                return {
                    "type": "intent",
                    "action": "move", 
                    "params": {"x": test_pos[0], "y": test_pos[1]},
                    "reasoning": f"Unstuck diagonal maneuver: trying {test_pos}"
                }
        
        return None
    
    def _is_position_walkable(self, test_pos: Tuple[int, int], current_pos: Tuple[int, int], 
                             walkable_grid: List[List[bool]], light_radius: int) -> bool:
        """Check if a position is walkable based on the walkable grid."""
        if not walkable_grid:
            return False
        
        # Convert world coordinates to grid coordinates
        cx, cy = current_pos
        tx, ty = test_pos
        
        grid_x = (tx - cx) + light_radius
        grid_y = (ty - cy) + light_radius
        
        if 0 <= grid_x < len(walkable_grid[0]) and 0 <= grid_y < len(walkable_grid):
            return walkable_grid[grid_y][grid_x]
        
        return False
    
    def _handle_no_path(self, current_pos: Tuple[int, int], target_pos: Tuple[int, int],
                       walkable_grid: List[List[bool]], light_radius: int) -> Optional[Dict[str, Any]]:
        """Handle case where no path is found to target."""
        # Try to get closer to target even if full path isn't available
        direction_x = 1 if target_pos[0] > current_pos[0] else -1 if target_pos[0] < current_pos[0] else 0
        direction_y = 1 if target_pos[1] > current_pos[1] else -1 if target_pos[1] < current_pos[1] else 0
        
        # Try moving in the general direction
        intermediate_pos = (current_pos[0] + direction_x * 3, current_pos[1] + direction_y * 3)
        
        if self._is_position_walkable(intermediate_pos, current_pos, walkable_grid, light_radius):
            return {
                "type": "intent",
                "action": "move",
                "params": {"x": intermediate_pos[0], "y": intermediate_pos[1]},
                "reasoning": f"No direct path found, moving toward target: {intermediate_pos}"
            }
        
        return None
    
    def get_navigation_status(self) -> Dict[str, Any]:
        """Get current navigation status for debugging."""
        return {
            'has_current_path': len(self.current_path) > 0,
            'waypoint_progress': f"{self.current_waypoint_index}/{len(self.current_path)}",
            'stuck_counter': self.stuck_counter,
            'is_stuck': self.stuck_counter > 5,
            'path_recalc_needed': self.path_recalc_needed,
            'current_path_length': len(self.current_path),
            'blocked_edges_cached': len(self.blocked_edges)
        }


# Standalone navigation function
def robust_navigation(current_pos: Tuple[int, int], target_pos: Tuple[int, int], 
                     walkable_grid: List[List[bool]], light_radius: int,
                     memory: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Standalone robust navigation function.
    
    Args:
        current_pos: Current position (x, y)
        target_pos: Target position (x, y)
        walkable_grid: 2D walkability grid
        light_radius: Vision radius
        memory: Optional memory dict to maintain state
        
    Returns:
        Dict with 'action' (intent), 'memory' (updated), and 'status'
    """
    if memory is None:
        memory = {'navigator': NavigationPlanner()}
    
    if 'navigator' not in memory:
        memory['navigator'] = NavigationPlanner()
    
    navigator = memory['navigator']
    action = navigator.plan_route(current_pos, target_pos, walkable_grid, light_radius)
    status = navigator.get_navigation_status()
    
    return {
        'action': action,
        'memory': memory,
        'status': status
    }


# Example usage and testing
if __name__ == "__main__":
    # Test the navigation system
    navigator = NavigationPlanner()
    
    # Create a simple walkable grid (21x21 centered on player)
    light_radius = 10
    grid_size = (light_radius * 2) + 1
    walkable_grid = [[True for _ in range(grid_size)] for _ in range(grid_size)]
    
    # Add some obstacles
    for i in range(5, 15):
        walkable_grid[10][i] = False  # horizontal wall
    walkable_grid[10][12] = True  # gap in wall
    
    current_pos = (50, 50)
    target_pos = (60, 55)  # Across the wall
    
    action = navigator.plan_route(current_pos, target_pos, walkable_grid, light_radius)
    print("Navigation action:", json.dumps(action, indent=2))
    
    status = navigator.get_navigation_status()
    print("Navigation status:", json.dumps(status, indent=2))
    
    # Test stuck detection
    print("\\nTesting stuck detection...")
    for _ in range(7):  # Simulate being stuck
        action = navigator.plan_route(current_pos, target_pos, walkable_grid, light_radius)
        if action and "Unstuck" in action.get('reasoning', ''):
            print("Stuck detection triggered:", action['reasoning'])
            break
    
    # Test standalone function
    result = robust_navigation((25, 25), (35, 35), walkable_grid, light_radius)
    print("\\nStandalone navigation:", json.dumps({
        'has_action': result['action'] is not None,
        'status': result['status']
    }, indent=2))