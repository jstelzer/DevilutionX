"""
Symbolic memory store for GAP agent
Provides persistent spatial/temporal memory without embeddings

This replaces the stateless LLM approach with a proper memory system:
- Facts: Key-value store for persistent knowledge
- Areas: Spatial memory of explored tiles
- Encounters: Combat history
- Goals: Task tracking with status

No vector DB needed - just fast SQL queries!
"""

import sqlite3
from typing import List, Tuple, Optional, Dict, Any
import time
import logging

logger = logging.getLogger(__name__)


class MemoryStore:
    """Persistent memory store using SQLite"""

    def __init__(self, db_path="gap_memory.db"):
        """Initialize memory store with SQLite backend"""
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._initialize_schema()
        logger.info(f"Memory store initialized: {db_path}")

    def _initialize_schema(self):
        """Create tables if they don't exist"""
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            -- Persistent facts (key-value store)
            CREATE TABLE IF NOT EXISTS facts(
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at INTEGER
            );

            -- Spatial memory (explored areas)
            CREATE TABLE IF NOT EXISTS areas(
                floor INTEGER,
                x INTEGER,
                y INTEGER,
                note TEXT,
                discovered_at INTEGER,
                PRIMARY KEY(floor, x, y)
            );

            -- Combat history
            CREATE TABLE IF NOT EXISTS encounters(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mob_kind TEXT,
                x INTEGER,
                y INTEGER,
                outcome TEXT,
                tick INTEGER
            );

            -- Goal tracking
            CREATE TABLE IF NOT EXISTS goals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                args TEXT,
                status TEXT,
                created_at INTEGER,
                updated_at INTEGER
            );

            -- Indices for fast lookups
            CREATE INDEX IF NOT EXISTS idx_areas_floor ON areas(floor);
            CREATE INDEX IF NOT EXISTS idx_areas_coords ON areas(floor, x, y);
            CREATE INDEX IF NOT EXISTS idx_encounters_tick ON encounters(tick);
            CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
        """)
        self.db.commit()

    # ========== Facts (Key-Value Store) ==========

    def set_fact(self, key: str, value: str, tick: int):
        """Store or update a persistent fact"""
        self.db.execute(
            "INSERT OR REPLACE INTO facts VALUES (?, ?, ?)",
            (key, value, tick)
        )
        self.db.commit()
        logger.debug(f"Set fact: {key}={value}")

    def get_fact(self, key: str) -> Optional[str]:
        """Retrieve a fact by key"""
        row = self.db.execute(
            "SELECT value FROM facts WHERE key=?",
            (key,)
        ).fetchone()
        return row[0] if row else None

    def get_all_facts(self) -> Dict[str, str]:
        """Get all facts as dictionary"""
        rows = self.db.execute("SELECT key, value FROM facts").fetchall()
        return {key: value for key, value in rows}

    # ========== Areas (Spatial Memory) ==========

    def mark_area_explored(self, floor: int, x: int, y: int, note: str, tick: int):
        """Record an explored area with optional note"""
        self.db.execute(
            "INSERT OR REPLACE INTO areas VALUES (?, ?, ?, ?, ?)",
            (floor, x, y, note, tick)
        )
        self.db.commit()

    def get_area_note(self, floor: int, x: int, y: int) -> Optional[str]:
        """Get note for specific area"""
        row = self.db.execute(
            "SELECT note FROM areas WHERE floor=? AND x=? AND y=?",
            (floor, x, y)
        ).fetchone()
        return row[0] if row else None

    def get_nearby_notes(self, floor: int, x: int, y: int, radius: int = 10) -> List[str]:
        """Get notes for areas near the given position"""
        rows = self.db.execute("""
            SELECT note FROM areas
            WHERE floor=?
              AND ABS(x-?) <= ?
              AND ABS(y-?) <= ?
              AND note IS NOT NULL
              AND note != ''
            ORDER BY ABS(x-?) + ABS(y-?) ASC
            LIMIT 5
        """, (floor, x, radius, y, radius, x, y)).fetchall()
        return [row[0] for row in rows]

    def is_area_explored(self, floor: int, x: int, y: int) -> bool:
        """Check if area has been explored"""
        row = self.db.execute(
            "SELECT 1 FROM areas WHERE floor=? AND x=? AND y=?",
            (floor, x, y)
        ).fetchone()
        return row is not None

    def get_unexplored_nearby(self, floor: int, x: int, y: int, radius: int = 20) -> List[Tuple[int, int]]:
        """Find nearby unexplored coordinates (for exploration goals)"""
        # This is a heuristic - we check a grid and see which tiles aren't in DB
        unexplored = []
        for dx in range(-radius, radius + 1, 5):  # Sample every 5 tiles
            for dy in range(-radius, radius + 1, 5):
                check_x, check_y = x + dx, y + dy
                if not self.is_area_explored(floor, check_x, check_y):
                    unexplored.append((check_x, check_y))
        return unexplored[:10]  # Return up to 10 candidates

    # ========== Encounters (Combat History) ==========

    def add_encounter(self, mob_kind: str, x: int, y: int, outcome: str, tick: int):
        """Record a combat encounter"""
        self.db.execute(
            "INSERT INTO encounters (mob_kind, x, y, outcome, tick) VALUES (?, ?, ?, ?, ?)",
            (mob_kind, x, y, outcome, tick)
        )
        self.db.commit()
        logger.debug(f"Recorded encounter: {mob_kind} at ({x},{y}) - {outcome}")

    def get_recent_encounters(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent combat encounters"""
        rows = self.db.execute("""
            SELECT mob_kind, x, y, outcome, tick
            FROM encounters
            ORDER BY tick DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [
            {"mob": mob, "x": x, "y": y, "outcome": outcome, "tick": tick}
            for mob, x, y, outcome, tick in rows
        ]

    def get_dangerous_areas(self, floor: int) -> List[Tuple[int, int, str]]:
        """Find areas with recent deaths/fleeing"""
        rows = self.db.execute("""
            SELECT x, y, mob_kind
            FROM encounters
            WHERE outcome IN ('death', 'fled')
            ORDER BY tick DESC
            LIMIT 5
        """).fetchall()
        return [(x, y, mob) for x, y, mob in rows]

    # ========== Goals (Task Tracking) ==========

    def add_goal(self, kind: str, args: str, tick: int) -> int:
        """Create a new goal, returns goal ID"""
        cursor = self.db.execute(
            "INSERT INTO goals (kind, args, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
            (kind, args, tick, tick)
        )
        self.db.commit()
        goal_id = cursor.lastrowid
        logger.info(f"Created goal #{goal_id}: {kind} {args}")
        return goal_id

    def update_goal_status(self, goal_id: int, status: str, tick: int):
        """Update goal status: 'active', 'completed', 'failed'"""
        self.db.execute(
            "UPDATE goals SET status=?, updated_at=? WHERE id=?",
            (status, tick, goal_id)
        )
        self.db.commit()
        logger.info(f"Goal #{goal_id} → {status}")

    def get_active_goals(self) -> List[Tuple[int, str, str]]:
        """Get all active goals (id, kind, args)"""
        rows = self.db.execute(
            "SELECT id, kind, args FROM goals WHERE status='active' ORDER BY created_at"
        ).fetchall()
        return rows

    def get_latest_goal(self) -> Optional[Tuple[int, str, str]]:
        """Get the most recent active goal"""
        row = self.db.execute("""
            SELECT id, kind, args FROM goals
            WHERE status='active'
            ORDER BY created_at DESC
            LIMIT 1
        """).fetchone()
        return row if row else None

    def clear_completed_goals(self, older_than_tick: int):
        """Clean up old completed goals"""
        self.db.execute(
            "DELETE FROM goals WHERE status='completed' AND updated_at < ?",
            (older_than_tick,)
        )
        self.db.commit()

    # ========== Maintenance ==========

    def cleanup_old_data(self, current_tick: int, retention_ticks: int = 100000):
        """Prune old encounter data to prevent DB bloat"""
        cutoff = current_tick - retention_ticks
        deleted = self.db.execute(
            "DELETE FROM encounters WHERE tick < ?",
            (cutoff,)
        ).rowcount
        self.db.commit()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old encounters")

    def get_stats(self) -> Dict[str, int]:
        """Get memory store statistics"""
        stats = {}
        stats['facts'] = self.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        stats['areas'] = self.db.execute("SELECT COUNT(*) FROM areas").fetchone()[0]
        stats['encounters'] = self.db.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
        stats['active_goals'] = self.db.execute("SELECT COUNT(*) FROM goals WHERE status='active'").fetchone()[0]
        stats['db_size_kb'] = self.db.execute("SELECT page_count * page_size / 1024 FROM pragma_page_count(), pragma_page_size()").fetchone()[0]
        return stats

    def close(self):
        """Close database connection"""
        self.db.close()
        logger.info("Memory store closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Helper functions for common memory patterns

def create_exploration_goal(memory: MemoryStore, floor: int, x: int, y: int, tick: int) -> int:
    """Create an exploration goal for a specific area"""
    return memory.add_goal("explore", f"floor={floor} target={x},{y}", tick)


def record_combat_victory(memory: MemoryStore, mob_name: str, x: int, y: int, tick: int):
    """Record a successful combat encounter"""
    memory.add_encounter(mob_name, x, y, "victory", tick)


def record_combat_death(memory: MemoryStore, mob_name: str, x: int, y: int, tick: int):
    """Record a death (danger area)"""
    memory.add_encounter(mob_name, x, y, "death", tick)


def mark_dangerous_area(memory: MemoryStore, floor: int, x: int, y: int, reason: str, tick: int):
    """Mark an area as dangerous"""
    memory.mark_area_explored(floor, x, y, f"DANGER: {reason}", tick)


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    with MemoryStore("test_memory.db") as mem:
        tick = 1000

        # Test facts
        mem.set_fact("current_floor", "2", tick)
        mem.set_fact("portal_location", "25,30", tick)
        print(f"Portal: {mem.get_fact('portal_location')}")

        # Test areas
        mem.mark_area_explored(2, 34, 18, "cleared", tick)
        mem.mark_area_explored(2, 38, 16, "danger_skeletons", tick)
        notes = mem.get_nearby_notes(2, 35, 17, radius=5)
        print(f"Nearby notes: {notes}")

        # Test encounters
        mem.add_encounter("Skeleton", 38, 16, "victory", tick)
        mem.add_encounter("Zombie", 36, 17, "victory", tick + 10)
        recent = mem.get_recent_encounters(5)
        print(f"Recent encounters: {recent}")

        # Test goals
        goal_id = mem.add_goal("explore", "cathedral_2", tick)
        mem.add_goal("clear_room", "x=40,y=20", tick + 5)
        active = mem.get_active_goals()
        print(f"Active goals: {active}")

        # Update goal
        mem.update_goal_status(goal_id, "completed", tick + 20)

        # Stats
        stats = mem.get_stats()
        print(f"Memory stats: {stats}")

    print("\n✅ Memory store test complete!")
