"""
Personality Persistence Store

Enables companion AI to remember experiences, learn strategies, and evolve personality across sessions.
"""

import sqlite3
import json
import time
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PersonalityStore:
    """
    SQLite-backed personality database for persistent companion state.

    Tracks:
    - Personality traits (risk_tolerance, player_relationship, etc.)
    - Episodic memories (deaths, victories, gifts, conversations)
    - Learned strategies (what works, what doesn't)
    - Prompt injections (context for agent decision-making)
    - Session reflections (end-of-session summaries)
    """

    def __init__(self, db_path="gap_personality.db", character_id: str = "Unknown"):
        """
        Initialize personality store.

        Args:
            db_path: Path to SQLite database file
            character_id: Unique character identifier (e.g., "Rogue_5", "Warrior_3")
        """
        self.db_path = db_path
        self.character_id = character_id
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.session_id = f"session_{int(time.time())}"
        self.session_start = int(time.time())

        self._init_schema()
        logger.info(f"📚 PersonalityStore initialized: {db_path}")
        logger.info(f"   Character: {self.character_id} (session: {self.session_id})")

    def _init_schema(self):
        """Create tables if not exist"""
        schema_path = Path(__file__).parent / "schema" / "personality.sql"

        if not schema_path.exists():
            logger.error(f"Schema file not found: {schema_path}")
            raise FileNotFoundError(f"Missing schema: {schema_path}")

        with open(schema_path, "r") as f:
            self.db.executescript(f.read())

        logger.debug("Personality schema initialized")

    def load_personality(self) -> Dict:
        """
        Load current personality state for prompt injection.

        Returns:
            {
                "traits": {"risk_tolerance": "cautious", ...},
                "memories": [recent memories],
                "strategies": [top strategies]
            }
        """
        traits = self._load_traits()
        recent_memories = self._load_recent_memories(limit=5)
        top_strategies = self._load_top_strategies(limit=3)

        personality = {
            "traits": traits,
            "memories": recent_memories,
            "strategies": top_strategies
        }

        logger.info(f"📚 Loaded personality: {len(traits)} traits, {len(recent_memories)} memories, {len(top_strategies)} strategies")
        return personality

    def _load_traits(self) -> Dict[str, Dict]:
        """Load all personality traits for this character"""
        cursor = self.db.execute("""
            SELECT trait_name, trait_value, confidence, last_updated, context
            FROM personality_traits
            WHERE character_id = ?
            ORDER BY last_updated DESC
        """, (self.character_id,))

        traits = {}
        for row in cursor.fetchall():
            traits[row['trait_name']] = {
                "value": row['trait_value'],
                "confidence": row['confidence'],
                "last_updated": row['last_updated'],
                "context": row['context']
            }

        return traits

    def _load_recent_memories(self, limit: int = 5) -> List[Dict]:
        """Load recent episodic memories for this character"""
        cursor = self.db.execute("""
            SELECT memory_type, description, emotional_impact, location, actor, timestamp
            FROM memories
            WHERE character_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (self.character_id, limit))

        memories = []
        for row in cursor.fetchall():
            memories.append({
                "type": row['memory_type'],
                "description": row['description'],
                "impact": row['emotional_impact'],
                "location": row['location'],
                "actor": row['actor'],
                "timestamp": row['timestamp']
            })

        return memories

    def _load_top_strategies(self, limit: int = 3) -> List[Dict]:
        """Load top learned strategies by success rate for this character"""
        cursor = self.db.execute("""
            SELECT situation, strategy, success_count, failure_count,
                   CAST(success_count AS REAL) / NULLIF(success_count + failure_count, 0) as confidence
            FROM learned_strategies
            WHERE character_id = ? AND success_count + failure_count > 0
            ORDER BY confidence DESC, success_count DESC
            LIMIT ?
        """, (self.character_id, limit))

        strategies = []
        for row in cursor.fetchall():
            strategies.append({
                "situation": row['situation'],
                "strategy": row['strategy'],
                "success_count": row['success_count'],
                "failure_count": row['failure_count'],
                "confidence": row['confidence'] or 0.0
            })

        return strategies

    def update_trait(self, name: str, value: str, confidence: float, context: str):
        """
        Update or insert personality trait.

        Args:
            name: Trait name (e.g., "risk_tolerance", "player_relationship")
            value: Trait value (e.g., "cautious", "trusting")
            confidence: Confidence level 0.0-1.0
            context: Why was this learned?
        """
        self.db.execute("""
            INSERT OR REPLACE INTO personality_traits
            (character_id, trait_name, trait_value, confidence, last_updated, context, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (self.character_id, name, value, confidence, int(time.time()), context, self.session_id))
        self.db.commit()

        logger.info(f"🧠 Trait updated: {name} = {value} (confidence: {confidence:.2f}, reason: {context})")

    def add_memory(self, memory_type: str, description: str,
                   emotional_impact: float, location: str, actor: str,
                   context: Optional[Dict] = None):
        """
        Add episodic memory.

        Args:
            memory_type: "death", "victory", "gift", "conversation", etc.
            description: Human-readable summary
            emotional_impact: -1.0 to 1.0 (negative = bad, positive = good)
            location: Where did this happen? "level_4", "town", etc.
            actor: Who was involved? "Butcher", "Player", "Griswold"
            context: Optional JSON dict with details
        """
        self.db.execute("""
            INSERT INTO memories
            (character_id, timestamp, session_id, memory_type, description, emotional_impact,
             location, actor, context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (self.character_id, int(time.time()), self.session_id, memory_type, description,
              emotional_impact, location, actor, json.dumps(context or {})))
        self.db.commit()

        impact_emoji = "💔" if emotional_impact < -0.5 else "😊" if emotional_impact > 0.5 else "📝"
        logger.info(f"{impact_emoji} Memory: {memory_type} - {description} (impact: {emotional_impact:+.1f})")

    def add_strategy(self, situation: str, strategy: str, success: bool):
        """
        Record strategy use and outcome.

        Args:
            situation: What was the situation? "facing_butcher", "low_hp_surrounded"
            strategy: What strategy was used? "retreat_to_stairs", "teleport_to_town"
            success: Did it work?
        """
        # Get existing strategy record for this character
        cursor = self.db.execute("""
            SELECT success_count, failure_count
            FROM learned_strategies
            WHERE character_id = ? AND situation = ? AND strategy = ?
        """, (self.character_id, situation, strategy))

        row = cursor.fetchone()

        if row:
            # Update existing
            success_count = row['success_count'] + (1 if success else 0)
            failure_count = row['failure_count'] + (0 if success else 1)

            self.db.execute("""
                UPDATE learned_strategies
                SET success_count = ?, failure_count = ?, last_used = ?,
                    confidence = CAST(? AS REAL) / (? + ?)
                WHERE character_id = ? AND situation = ? AND strategy = ?
            """, (success_count, failure_count, int(time.time()),
                  success_count, success_count, failure_count,
                  self.character_id, situation, strategy))
        else:
            # Insert new
            success_count = 1 if success else 0
            failure_count = 0 if success else 1
            confidence = 1.0 if success else 0.0

            self.db.execute("""
                INSERT INTO learned_strategies
                (character_id, situation, strategy, success_count, failure_count, last_used, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (self.character_id, situation, strategy, success_count, failure_count, int(time.time()), confidence))

        self.db.commit()

        result_emoji = "✅" if success else "❌"
        logger.info(f"{result_emoji} Strategy: {situation} → {strategy}")

    def add_prompt_injection(self, agent_name: str, priority: int, content: str, reason: str):
        """
        Add prompt injection for agent.

        Args:
            agent_name: "combat", "chat", "healing", "all"
            priority: Higher = injected earlier (more important)
            content: Text to inject into prompt
            reason: Why was this added?
        """
        self.db.execute("""
            INSERT INTO prompt_injections
            (character_id, agent_name, priority, content, active, created_at, reason)
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (self.character_id, agent_name, priority, content, int(time.time()), reason))
        self.db.commit()

        logger.info(f"💉 Prompt injection added: {agent_name} (priority {priority})")

    def get_prompt_context(self, agent_name: str) -> str:
        """
        Generate personality context for agent prompt.

        Args:
            agent_name: Agent requesting context

        Returns:
            Multi-line string to inject into prompt
        """
        # Get active injections for this agent and character
        cursor = self.db.execute("""
            SELECT content FROM prompt_injections
            WHERE character_id = ?
              AND (agent_name = ? OR agent_name = 'all')
              AND active = 1
            ORDER BY priority DESC
        """, (self.character_id, agent_name))

        injections = [row['content'] for row in cursor.fetchall()]

        if injections:
            context = "\n".join(injections)
            logger.debug(f"💬 Prompt context for {agent_name}: {len(injections)} injections")
            return context
        else:
            return ""

    def save_session_reflection(self, reflection: str, stats: Dict):
        """
        Save end-of-session reflection.

        Args:
            reflection: LLM-generated session summary
            stats: Session statistics dict
        """
        self.db.execute("""
            INSERT INTO session_reflections
            (session_id, character_id, start_time, end_time, reflection, stats)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            self.session_id,
            self.character_id,
            self.session_start,
            int(time.time()),
            reflection,
            json.dumps(stats)
        ))
        self.db.commit()

        logger.info(f"📖 Session reflection saved: {self.session_id}")

    def close(self):
        """Close database connection"""
        self.db.close()
        logger.info(f"📚 PersonalityStore closed: {self.session_id}")
