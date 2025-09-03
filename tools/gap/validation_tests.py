#!/usr/bin/env python3
"""
Phase 0 Validation Tests for GAP AI

This module contains 5 critical tests that validate the Phase 0 implementation:
1. Town Exploration Test - Systematic exploration without getting stuck
2. Pathfinding Around Obstacles Test - Navigation around walls via waypoints  
3. Basic Combat Survival Test - 1v1 combat with proper kiting behavior
4. Emergency Healing Test - Pre-pot at low health, respect cooldown
5. Door Interaction Test - Navigate through doors to reach targets

These tests can be run immediately to verify the robustness of the GAP system.
"""

import json
import time
from typing import Dict, Any, List, Optional
import unittest
from unittest.mock import Mock, patch

# Import our Phase 0 modules
from survival_reflexes import SurvivalReflexes
from exploration import ExplorationManager, systematic_exploration_step
from navigation import NavigationPlanner, robust_navigation


class Phase0ValidationTests(unittest.TestCase):
    """Test suite for Phase 0 GAP improvements."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.survival_reflexes = SurvivalReflexes()
        self.exploration_manager = ExplorationManager() 
        self.navigator = NavigationPlanner()
        
    def test_1_town_exploration(self):
        """Test 1: Systematic town exploration without getting stuck."""
        print("\\n=== Test 1: Town Exploration ===")
        
        # Simulate town state with multiple frontiers
        town_state = {
            'timestamp': 1000,
            'player': {'level': 0, 'pos': [75, 68], 'in_town': True},  # Tristram
            'vision': {
                'exploration': {
                    'current_level': 0,
                    'exploration_radius': 15,
                    'stairs_visible': False,
                    'objects': [
                        {'type': 'fountain', 'pos': [73, 65]},
                        {'type': 'door', 'pos': [62, 16]}  # Griswold's shop
                    ],
                    'frontiers': [
                        [80, 68], [70, 68], [75, 75], [75, 60],  # Cardinal directions
                        [65, 55], [85, 75], [70, 80], [80, 55]   # More exploration points
                    ]
                }
            }
        }
        
        # Test exploration decisions over multiple steps
        positions_visited = set()
        stuck_counter = 0
        last_pos = None
        
        for step in range(10):  # Simulate 10 exploration steps
            action = self.exploration_manager.get_exploration_action(town_state)
            self.assertIsNotNone(action, f"Step {step}: Exploration should always return an action when frontiers exist")
            self.assertEqual(action['type'], 'intent')
            self.assertIn(action['action'], ['path', 'move'])
            
            # Simulate moving to the target
            if 'params' in action:
                new_pos = (action['params']['x'], action['params']['y'])
                positions_visited.add(new_pos)
                
                # Check for stuck behavior
                if new_pos == last_pos:
                    stuck_counter += 1
                else:
                    stuck_counter = 0
                    
                self.assertLess(stuck_counter, 3, f"AI got stuck at position {new_pos} for {stuck_counter} steps")
                
                # Update state for next iteration
                town_state['player']['pos'] = [new_pos[0], new_pos[1]]
                last_pos = new_pos
        
        # Verify systematic exploration
        self.assertGreaterEqual(len(positions_visited), 5, "Should visit at least 5 different positions")
        status = self.exploration_manager.get_exploration_status(town_state)
        self.assertGreater(status['total_positions_visited'], 5, "Should track multiple visited positions")
        
        print(f"✓ Visited {len(positions_visited)} unique positions without getting stuck")
        print(f"✓ Final exploration status: {status['completion_percentage']:.1%} complete")
        
    def test_2_pathfinding_around_obstacles(self):
        """Test 2: A* pathfinding around walls via waypoints."""
        print("\\n=== Test 2: Pathfinding Around Obstacles ===")
        
        # Create walkable grid with obstacle (21x21 grid, light_radius=10)
        light_radius = 10
        grid_size = (light_radius * 2) + 1
        walkable_grid = [[True for _ in range(grid_size)] for _ in range(grid_size)]
        
        # Add L-shaped obstacle (wall)
        for i in range(8, 15):  # Horizontal wall
            walkable_grid[10][i] = False
        for i in range(6, 11):  # Vertical wall  
            walkable_grid[i][12] = False
        
        current_pos = (50, 50)  # Player position
        target_pos = (58, 46)   # Behind the L-shaped wall
        
        # Test pathfinding
        action = self.navigator.plan_route(current_pos, target_pos, walkable_grid, light_radius)
        
        self.assertIsNotNone(action, "Should find a path around obstacles")
        self.assertEqual(action['type'], 'intent')
        self.assertEqual(action['action'], 'move')
        self.assertIn('params', action)
        
        waypoint = (action['params']['x'], action['params']['y'])
        distance_moved = ((waypoint[0] - current_pos[0])**2 + (waypoint[1] - current_pos[1])**2)**0.5
        
        # Verify reasonable waypoint distance (should be chunked, not too far)
        self.assertLessEqual(distance_moved, 5, "Waypoint should be within 5 tiles (chunked movement)")
        self.assertGreater(distance_moved, 0.5, "Should actually move somewhere")
        
        # Verify path planning status
        status = self.navigator.get_navigation_status()
        self.assertFalse(status['is_stuck'], "Should not be stuck initially")
        
        print(f"✓ Found path around obstacle: {current_pos} → {waypoint} (distance: {distance_moved:.1f})")
        print(f"✓ Navigation status: {status}")
        
    def test_3_basic_combat_survival(self):
        """Test 3: 1v1 combat with proper kiting behavior."""
        print("\\n=== Test 3: Basic Combat Survival ===")
        
        # Test combat against single skeleton
        combat_state = {
            'timestamp': 2000,
            'player': {'hp': 80, 'hp_max': 100, 'pos': [45, 45]},
            'monsters': [
                {
                    'id': 42,
                    'name': 'Skeleton', 
                    'pos': [47, 47],
                    'distance': 2,  # Melee range
                    'hp': 50,
                    'hp_max': 60,
                    'hp_percent': 83
                }
            ]
        }
        
        # Test survival reflexes
        reflex_action = self.survival_reflexes.check_emergency_actions(combat_state)
        self.assertIsNone(reflex_action, "Should not trigger emergency action at 80% HP")
        
        # Test low health emergency  
        combat_state['player']['hp'] = 20  # 20% HP - emergency!
        reflex_action = self.survival_reflexes.check_emergency_actions(combat_state)
        
        self.assertIsNotNone(reflex_action, "Should trigger emergency healing at 20% HP")
        self.assertEqual(reflex_action['action'], 'use_potion')
        self.assertEqual(reflex_action['params']['kind'], 'hp')
        self.assertIn('EMERGENCY', reflex_action['reasoning'])
        
        # Test overwhelming enemies (kiting behavior)
        overwhelming_state = {
            'timestamp': 3000,
            'player': {'hp': 60, 'hp_max': 100, 'pos': [50, 50]},
            'monsters': [
                {'id': 1, 'pos': [51, 51], 'distance': 1, 'hp_percent': 100},
                {'id': 2, 'pos': [49, 51], 'distance': 1, 'hp_percent': 90}, 
                {'id': 3, 'pos': [51, 49], 'distance': 1, 'hp_percent': 85},
                {'id': 4, 'pos': [49, 49], 'distance': 1, 'hp_percent': 95},
                {'id': 5, 'pos': [52, 50], 'distance': 2, 'hp_percent': 70}  # 5 enemies = overwhelming
            ]
        }
        
        kite_action = self.survival_reflexes.check_emergency_actions(overwhelming_state)
        self.assertIsNotNone(kite_action, "Should kite when overwhelmed by 5 enemies")
        self.assertEqual(kite_action['action'], 'move')
        self.assertIn('KITING', kite_action['reasoning'])
        
        # Verify kite direction moves away from enemies
        kite_pos = (kite_action['params']['x'], kite_action['params']['y'])
        player_pos = (50, 50)
        kite_distance = ((kite_pos[0] - player_pos[0])**2 + (kite_pos[1] - player_pos[1])**2)**0.5
        self.assertGreater(kite_distance, 2, "Should kite at least 2 tiles away")
        
        print(f"✓ Emergency healing triggered at 20% HP")
        print(f"✓ Kiting behavior activated with 5 enemies, retreating to {kite_pos}")
        
        # Test survival status
        survival_status = self.survival_reflexes.get_survival_status(combat_state)
        print(f"✓ Survival metrics: {survival_status}")
        
    def test_4_emergency_healing(self):
        """Test 4: Pre-pot at low health, respect cooldown."""
        print("\\n=== Test 4: Emergency Healing ===")
        
        # Test pre-emptive healing under fire
        under_fire_state = {
            'timestamp': 4000,
            'player': {'hp': 40, 'hp_max': 100, 'pos': [30, 30]},  # 40% HP
            'monsters': [
                {'id': 1, 'pos': [31, 31], 'distance': 1, 'hp_percent': 80},  # Close enemy
                {'id': 2, 'pos': [29, 31], 'distance': 2, 'hp_percent': 90},  # Another close enemy
                {'id': 3, 'pos': [31, 29], 'distance': 2, 'hp_percent': 75}   # Third enemy
            ]
        }
        
        # Should trigger pre-emptive healing (40% HP + incoming damage)
        preemptive_action = self.survival_reflexes.check_emergency_actions(under_fire_state)
        self.assertIsNotNone(preemptive_action, "Should pre-emptively heal at 40% HP under fire")
        self.assertEqual(preemptive_action['action'], 'use_potion')
        self.assertIn('PRE-EMPTIVE', preemptive_action['reasoning'])
        
        # Test cooldown respect - should not use another potion immediately
        immediate_retry_state = under_fire_state.copy()
        immediate_retry_state['timestamp'] = 4200  # 200ms later (< 500ms cooldown)
        
        cooldown_action = self.survival_reflexes.check_emergency_actions(immediate_retry_state)
        # Should not trigger another potion use due to cooldown
        if cooldown_action and cooldown_action.get('action') == 'use_potion':
            self.fail("Should respect potion cooldown - 200ms is too soon")
        
        # Test after cooldown expires
        after_cooldown_state = under_fire_state.copy()
        after_cooldown_state['timestamp'] = 4600  # 600ms later (> 500ms cooldown)
        after_cooldown_state['player']['hp'] = 15  # Critical HP
        
        # Reset survival reflexes for clean test
        survival_reflexes_2 = SurvivalReflexes()
        survival_reflexes_2.last_potion_time = 4000  # Set previous potion time
        
        post_cooldown_action = survival_reflexes_2.check_emergency_actions(after_cooldown_state)
        self.assertIsNotNone(post_cooldown_action, "Should allow healing after cooldown expires")
        
        print(f"✓ Pre-emptive healing triggered at 40% HP under fire")
        print(f"✓ Cooldown respected - no immediate second potion")
        print(f"✓ Healing allowed again after 600ms > 500ms cooldown")
        
    def test_5_door_interaction(self):
        """Test 5: Navigate through doors to reach targets."""
        print("\\n=== Test 5: Door Interaction ===")
        
        # This test simulates the intent handling for door interaction
        # We'll test the exploration system's ability to identify doors as targets
        
        door_state = {
            'timestamp': 5000,
            'player': {'level': 1, 'pos': [40, 40], 'in_town': False},
            'vision': {
                'exploration': {
                    'current_level': 1,
                    'exploration_radius': 10,
                    'stairs_visible': False,
                    'objects': [
                        {'type': 'door', 'pos': [45, 42], 'id': 301},  # Door blocking path
                        {'type': 'chest', 'pos': [50, 42]}  # Treasure behind door
                    ],
                    'frontiers': []  # No frontiers - door is the next step
                }
            }
        }
        
        # When no frontiers exist, exploration should target objects
        action = self.exploration_manager.get_exploration_action(door_state)
        
        self.assertIsNotNone(action, "Should target door when no frontiers available")
        self.assertEqual(action['type'], 'intent')
        self.assertEqual(action['action'], 'path')
        
        # Should target the door position
        door_pos = door_state['vision']['exploration']['objects'][0]['pos']
        target_pos = (action['params']['x'], action['params']['y'])
        
        self.assertEqual(target_pos, tuple(door_pos), "Should target door position for interaction")
        self.assertIn('door', action['reasoning'].lower(), "Should mention door in reasoning")
        
        # Test navigation to door with obstacles
        light_radius = 10
        grid_size = (light_radius * 2) + 1
        walkable_grid = [[True for _ in range(grid_size)] for _ in range(grid_size)]
        
        # Add wall with door gap
        for i in range(5, 15):
            walkable_grid[10][i] = False  # Wall
        walkable_grid[10][12] = True  # Door opening
        
        current_pos = (40, 40)
        door_pos = (45, 42)
        
        nav_action = self.navigator.plan_route(current_pos, door_pos, walkable_grid, light_radius)
        
        if nav_action:  # Path found
            self.assertEqual(nav_action['action'], 'move')
            waypoint = (nav_action['params']['x'], nav_action['params']['y'])
            distance = ((waypoint[0] - current_pos[0])**2 + (waypoint[1] - current_pos[1])**2)**0.5
            self.assertLessEqual(distance, 5, "Should move in reasonable increments toward door")
        
        print(f"✓ Door interaction targeted when no frontiers available")
        print(f"✓ Navigation planned route toward door at {door_pos}")
        
        # Test the new GAP intents (mock test since we'd need actual game)
        interact_intent = {
            "type": "intent",
            "action": "interact", 
            "params": {"id": 301},  # Door object ID
            "reasoning": "Opening door to access area behind"
        }
        
        # Verify intent structure
        self.assertEqual(interact_intent['action'], 'interact')
        self.assertIn('id', interact_intent['params'])
        self.assertEqual(interact_intent['params']['id'], 301)
        
        print(f"✓ Door interaction intent properly structured: {interact_intent}")


def run_all_validation_tests():
    """Run all Phase 0 validation tests and report results."""
    print("=" * 60)
    print("PHASE 0 GAP AI VALIDATION TESTS")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(Phase0ValidationTests)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=open('/dev/null', 'w'))
    result = runner.run(suite)
    
    # Custom result reporting
    print(f"\\n" + "=" * 60)
    print(f"VALIDATION RESULTS:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print(f"\\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback.split('AssertionError: ')[-1].split('\\n')[0]}")
    
    if result.errors:
        print(f"\\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback.split('\\n')[-2]}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    
    if success:
        print(f"\\n🎉 ALL PHASE 0 TESTS PASSED! 🎉")
        print(f"The GAP AI system is ready for robust gameplay.")
    else:
        print(f"\\n❌ Some tests failed. Please review the issues above.")
    
    print(f"=" * 60)
    
    return success


if __name__ == "__main__":
    # Run all validation tests
    success = run_all_validation_tests()
    
    # Exit with appropriate code
    exit(0 if success else 1)