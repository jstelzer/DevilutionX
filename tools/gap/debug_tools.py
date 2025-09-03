#!/usr/bin/env python3
"""
Debug Tools for GAP AI Development

This module provides essential debugging and development ergonomics for the GAP AI system:
1. State/Action Replay Logging - Record and replay game sessions for debugging
2. Performance Monitoring - Track AI decision timing and efficiency
3. Decision Tree Visualization - See why the AI made specific choices
4. Error Analysis - Categorize and analyze failure modes
5. Development Shortcuts - Quick testing and debugging utilities

Key Features:
- JSON-based replay format for easy analysis
- Real-time performance metrics
- Decision reasoning chains
- Automatic error categorization
- Development server for live debugging
"""

import json
import time
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import threading
import gzip
from pathlib import Path


class ReplayLogger:
    """Records game sessions for debugging and analysis."""
    
    def __init__(self, log_dir: str = "gap_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Current session data
        self.session_id = None
        self.session_data = []
        self.session_start = None
        self.auto_save_interval = 30  # seconds
        self.last_save = 0
        
        # Performance tracking
        self.decision_times = []
        self.action_counts = {}
        self.error_log = []
        
    def start_session(self, session_name: Optional[str] = None) -> str:
        """Start a new replay logging session."""
        if session_name is None:
            session_name = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        
        self.session_id = session_name
        self.session_start = time.time()
        self.session_data = []
        self.decision_times = []
        self.action_counts = {}
        self.error_log = []
        
        print(f"📽️  Started replay logging session: {session_name}")
        return session_name
    
    def log_state_action(self, timestamp: int, state: Dict[str, Any], 
                        action: Optional[Dict[str, Any]], reasoning: str = "",
                        decision_time_ms: float = 0):
        """Log a state-action pair with reasoning."""
        if not self.session_id:
            self.start_session()
        
        # Record decision timing
        if decision_time_ms > 0:
            self.decision_times.append(decision_time_ms)
        
        # Track action types
        if action:
            action_type = action.get('action', 'unknown')
            self.action_counts[action_type] = self.action_counts.get(action_type, 0) + 1
        
        # Create log entry
        log_entry = {
            "timestamp": timestamp,
            "game_time": time.time() - self.session_start,
            "state": self._compress_state(state),
            "action": action,
            "reasoning": reasoning,
            "decision_time_ms": decision_time_ms,
            "performance_snapshot": self._get_performance_snapshot()
        }
        
        self.session_data.append(log_entry)
        
        # Auto-save periodically
        if time.time() - self.last_save > self.auto_save_interval:
            self._auto_save()
    
    def log_error(self, error_type: str, error_msg: str, state: Optional[Dict[str, Any]] = None):
        """Log an error with context."""
        error_entry = {
            "timestamp": time.time(),
            "error_type": error_type,
            "error_message": error_msg,
            "state_context": self._compress_state(state) if state else None
        }
        
        self.error_log.append(error_entry)
        print(f"❌ GAP Error [{error_type}]: {error_msg}")
    
    def _compress_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Compress state data for efficient storage."""
        if not state:
            return {}
        
        # Keep essential data, compress others
        compressed = {}
        
        # Always keep these
        essential_keys = ['timestamp', 'player', 'monsters']
        for key in essential_keys:
            if key in state:
                compressed[key] = state[key]
        
        # Compress vision data
        if 'vision' in state:
            vision = state['vision']
            compressed['vision'] = {
                'exploration': {
                    'frontiers_count': len(vision.get('exploration', {}).get('frontiers', [])),
                    'objects_count': len(vision.get('exploration', {}).get('objects', [])),
                    'stairs_visible': vision.get('exploration', {}).get('stairs_visible', False)
                }
            }
        
        return compressed
    
    def _get_performance_snapshot(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        if not self.decision_times:
            return {}
        
        recent_times = self.decision_times[-10:]  # Last 10 decisions
        return {
            "avg_decision_time": sum(recent_times) / len(recent_times),
            "max_decision_time": max(recent_times),
            "total_decisions": len(self.decision_times),
            "actions_per_minute": len(self.session_data) / max((time.time() - self.session_start) / 60, 0.1)
        }
    
    def _auto_save(self):
        """Auto-save current session."""
        if self.session_data:
            self.save_session()
            self.last_save = time.time()
    
    def save_session(self, filename: Optional[str] = None):
        """Save current session to disk."""
        if not self.session_data:
            return
        
        if filename is None:
            filename = f"{self.session_id}.json.gz"
        
        filepath = self.log_dir / filename
        
        session_metadata = {
            "session_id": self.session_id,
            "start_time": self.session_start,
            "end_time": time.time(),
            "total_entries": len(self.session_data),
            "action_counts": self.action_counts,
            "performance_summary": {
                "avg_decision_time": sum(self.decision_times) / max(len(self.decision_times), 1),
                "total_errors": len(self.error_log)
            }
        }
        
        full_session_data = {
            "metadata": session_metadata,
            "entries": self.session_data,
            "errors": self.error_log
        }
        
        # Save compressed
        with gzip.open(filepath, 'wt') as f:
            json.dump(full_session_data, f, indent=1)
        
        print(f"💾 Saved session with {len(self.session_data)} entries to {filepath}")
        return filepath
    
    def load_session(self, filepath: str) -> Dict[str, Any]:
        """Load a saved session for analysis."""
        with gzip.open(filepath, 'rt') as f:
            return json.load(f)
    
    def analyze_session(self, filepath: str) -> Dict[str, Any]:
        """Analyze a saved session and generate insights."""
        session_data = self.load_session(filepath)
        entries = session_data['entries']
        metadata = session_data['metadata']
        
        # Analyze decision patterns
        reasoning_categories = {}
        for entry in entries:
            reasoning = entry.get('reasoning', 'unknown')
            category = self._categorize_reasoning(reasoning)
            reasoning_categories[category] = reasoning_categories.get(category, 0) + 1
        
        # Performance analysis
        decision_times = [e.get('decision_time_ms', 0) for e in entries if e.get('decision_time_ms', 0) > 0]
        
        analysis = {
            "session_info": metadata,
            "decision_patterns": reasoning_categories,
            "performance": {
                "total_decisions": len(entries),
                "avg_decision_time": sum(decision_times) / max(len(decision_times), 1),
                "slow_decisions": len([t for t in decision_times if t > 200]),  # >200ms
                "session_duration": metadata['end_time'] - metadata['start_time']
            },
            "error_summary": {
                "total_errors": len(session_data.get('errors', [])),
                "error_types": self._categorize_errors(session_data.get('errors', []))
            }
        }
        
        return analysis
    
    def _categorize_reasoning(self, reasoning: str) -> str:
        """Categorize AI reasoning for analysis."""
        reasoning = reasoning.lower()
        
        if 'emergency' in reasoning or 'critical' in reasoning:
            return 'emergency_response'
        elif 'exploration' in reasoning or 'frontier' in reasoning:
            return 'exploration'
        elif 'combat' in reasoning or 'attack' in reasoning:
            return 'combat'
        elif 'navigation' in reasoning or 'path' in reasoning:
            return 'navigation'
        elif 'kiting' in reasoning or 'retreat' in reasoning:
            return 'kiting'
        elif 'healing' in reasoning or 'potion' in reasoning:
            return 'survival'
        else:
            return 'other'
    
    def _categorize_errors(self, errors: List[Dict[str, Any]]) -> Dict[str, int]:
        """Categorize errors by type."""
        error_types = {}
        for error in errors:
            error_type = error.get('error_type', 'unknown')
            error_types[error_type] = error_types.get(error_type, 0) + 1
        return error_types


class PerformanceMonitor:
    """Monitor AI performance in real-time."""
    
    def __init__(self):
        self.metrics = {
            'decisions_per_second': 0,
            'avg_decision_time': 0,
            'stuck_counter': 0,
            'survival_events': 0,
            'exploration_efficiency': 0
        }
        self.history = []
        self.start_time = time.time()
        
    def update_metrics(self, decision_time: float, action_type: str, reasoning: str):
        """Update performance metrics."""
        current_time = time.time()
        
        # Update decision timing
        self.metrics['avg_decision_time'] = (
            self.metrics['avg_decision_time'] * 0.9 + decision_time * 0.1
        )
        
        # Track specific events
        if 'stuck' in reasoning.lower():
            self.metrics['stuck_counter'] += 1
        elif 'emergency' in reasoning.lower() or 'healing' in reasoning.lower():
            self.metrics['survival_events'] += 1
        
        # Calculate decisions per second (rolling average)
        elapsed = current_time - self.start_time
        if elapsed > 0:
            total_decisions = len(self.history) + 1
            self.metrics['decisions_per_second'] = total_decisions / elapsed
        
        # Store history
        self.history.append({
            'timestamp': current_time,
            'decision_time': decision_time,
            'action_type': action_type,
            'reasoning': reasoning
        })
        
        # Keep last 1000 entries
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
    
    def get_status(self) -> Dict[str, Any]:
        """Get current performance status."""
        return {
            'current_metrics': self.metrics.copy(),
            'recent_performance': self._get_recent_performance(),
            'system_health': self._assess_system_health()
        }
    
    def _get_recent_performance(self) -> Dict[str, float]:
        """Get performance over last 60 seconds."""
        if not self.history:
            return {}
        
        recent_cutoff = time.time() - 60  # Last 60 seconds
        recent_entries = [e for e in self.history if e['timestamp'] > recent_cutoff]
        
        if not recent_entries:
            return {}
        
        decision_times = [e['decision_time'] for e in recent_entries]
        return {
            'recent_decisions': len(recent_entries),
            'recent_avg_time': sum(decision_times) / len(decision_times),
            'recent_max_time': max(decision_times),
            'recent_decisions_per_second': len(recent_entries) / 60
        }
    
    def _assess_system_health(self) -> str:
        """Assess overall system health."""
        if self.metrics['avg_decision_time'] > 500:  # >500ms average
            return 'SLOW'
        elif self.metrics['stuck_counter'] > 10:
            return 'STUCK_PRONE'  
        elif self.metrics['survival_events'] > 20:
            return 'HIGH_DANGER'
        else:
            return 'HEALTHY'


class DevelopmentTools:
    """Development utilities and shortcuts."""
    
    def __init__(self):
        self.replay_logger = ReplayLogger()
        self.performance_monitor = PerformanceMonitor()
        self.debug_mode = False
        
    def enable_debug_mode(self):
        """Enable verbose debugging."""
        self.debug_mode = True
        print("🐛 Debug mode enabled - verbose logging active")
    
    def quick_test_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """Quick test scenarios for development."""
        scenarios = {
            'town_start': {
                'timestamp': 1000,
                'player': {'level': 0, 'pos': [75, 68], 'hp': 100, 'hp_max': 100, 'in_town': True},
                'vision': {
                    'exploration': {
                        'current_level': 0,
                        'exploration_radius': 15,
                        'stairs_visible': False,
                        'objects': [{'type': 'fountain', 'pos': [73, 65]}],
                        'frontiers': [[80, 68], [70, 68], [75, 75], [75, 60]]
                    }
                },
                'monsters': []
            },
            'combat_emergency': {
                'timestamp': 2000,
                'player': {'level': 1, 'pos': [50, 50], 'hp': 15, 'hp_max': 100, 'in_town': False},
                'vision': {'exploration': {'frontiers': []}},
                'monsters': [
                    {'id': 1, 'pos': [51, 51], 'distance': 1, 'hp_percent': 80},
                    {'id': 2, 'pos': [49, 51], 'distance': 1, 'hp_percent': 90}
                ]
            },
            'exploration_complete': {
                'timestamp': 3000,
                'player': {'level': 2, 'pos': [40, 40], 'hp': 80, 'hp_max': 100, 'in_town': False},
                'vision': {
                    'exploration': {
                        'current_level': 2,
                        'exploration_radius': 15,
                        'stairs_visible': True,
                        'stairs_pos': [45, 45],
                        'stairs_type': 'down_next',
                        'objects': [],
                        'frontiers': []
                    }
                },
                'monsters': []
            }
        }
        
        return scenarios.get(scenario_name, {})
    
    def generate_performance_report(self) -> str:
        """Generate a formatted performance report."""
        status = self.performance_monitor.get_status()
        
        report = f"""
🎯 GAP AI Performance Report
{'='*40}
System Health: {status['system_health']}

Current Metrics:
- Avg Decision Time: {status['current_metrics']['avg_decision_time']:.1f}ms  
- Decisions/Second: {status['current_metrics']['decisions_per_second']:.2f}
- Stuck Events: {status['current_metrics']['stuck_counter']}
- Survival Events: {status['current_metrics']['survival_events']}

Recent Performance (60s):
- Recent Decisions: {status.get('recent_performance', {}).get('recent_decisions', 0)}
- Recent Avg Time: {status.get('recent_performance', {}).get('recent_avg_time', 0):.1f}ms
- Recent Max Time: {status.get('recent_performance', {}).get('recent_max_time', 0):.1f}ms

💡 Recommendations:
"""
        
        # Add recommendations based on metrics
        health = status['system_health']
        if health == 'SLOW':
            report += "- Consider optimizing decision algorithms\n- Check for expensive computations\n"
        elif health == 'STUCK_PRONE':
            report += "- Review pathfinding and obstacle detection\n- Check exploration algorithm efficiency\n"
        elif health == 'HIGH_DANGER':
            report += "- Review survival reflexes tuning\n- Consider more conservative strategies\n"
        else:
            report += "- System performing well! 🎉\n"
        
        return report
    
    def analyze_decision_chain(self, recent_count: int = 10) -> List[Dict[str, Any]]:
        """Analyze the last N decisions for debugging."""
        if not hasattr(self, '_decision_history'):
            self._decision_history = []
        
        return self._decision_history[-recent_count:]
    
    def log_decision(self, state: Dict[str, Any], action: Optional[Dict[str, Any]], 
                    reasoning: str, decision_time: float):
        """Log a decision for debugging analysis."""
        if not hasattr(self, '_decision_history'):
            self._decision_history = []
        
        decision_entry = {
            'timestamp': time.time(),
            'state_summary': self._summarize_state(state),
            'action': action,
            'reasoning': reasoning,
            'decision_time': decision_time
        }
        
        self._decision_history.append(decision_entry)
        
        # Keep last 100 decisions
        if len(self._decision_history) > 100:
            self._decision_history = self._decision_history[-100:]
        
        # Log to replay system
        self.replay_logger.log_state_action(
            state.get('timestamp', 0), state, action, reasoning, decision_time
        )
        
        # Update performance monitoring
        self.performance_monitor.update_metrics(
            decision_time, action.get('action', 'none') if action else 'none', reasoning
        )
        
        if self.debug_mode:
            print(f"🤔 Decision: {reasoning} -> {action.get('action', 'none') if action else 'none'} ({decision_time:.1f}ms)")
    
    def _summarize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Create a concise state summary for debugging."""
        player = state.get('player', {})
        monsters = state.get('monsters', [])
        
        return {
            'hp_ratio': player.get('hp', 0) / max(player.get('hp_max', 1), 1),
            'position': player.get('pos', [0, 0]),
            'level': player.get('level', 0),
            'enemy_count': len(monsters),
            'closest_enemy_distance': min([m.get('distance', 999) for m in monsters], default=999),
            'frontiers_available': len(state.get('vision', {}).get('exploration', {}).get('frontiers', []))
        }


# Global debug tools instance for easy access
debug_tools = DevelopmentTools()


# Example usage and testing
if __name__ == "__main__":
    # Test the debug tools
    tools = DevelopmentTools()
    tools.enable_debug_mode()
    
    # Test replay logging
    print("Testing replay logging...")
    tools.replay_logger.start_session("test_session")
    
    # Simulate some decisions
    test_state = tools.quick_test_scenario('town_start')
    test_action = {"type": "intent", "action": "move", "params": {"x": 80, "y": 68}}
    
    tools.log_decision(test_state, test_action, "Testing exploration in town", 45.2)
    tools.log_decision(test_state, None, "No action needed, safe in town", 12.1)
    
    # Save session
    filepath = tools.replay_logger.save_session()
    print(f"Saved test session to: {filepath}")
    
    # Generate performance report
    print("\nPerformance Report:")
    print(tools.generate_performance_report())
    
    # Analyze session
    if filepath.exists():
        analysis = tools.replay_logger.analyze_session(str(filepath))
        print(f"\nSession Analysis: {json.dumps(analysis, indent=2)}")