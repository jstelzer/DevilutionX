#!/usr/bin/env python3
"""
View personality database contents.

Usage:
    python3 view_personality.py [db_path] [character_id]

Examples:
    python3 view_personality.py                    # All characters
    python3 view_personality.py gap_personality.db # All characters in specific DB
    python3 view_personality.py gap_personality.db Rogue_5  # Only Rogue level 5

Default path: gap_personality.db
"""

import sys
import sqlite3
import json
from pathlib import Path


def format_timestamp(ts: int) -> str:
    """Format unix timestamp to readable string"""
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def view_personality(db_path: str = "gap_personality.db", character_id: str = None):
    """Display personality database contents in human-readable format"""

    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        print(f"\nExpected location: {Path(db_path).absolute()}")
        return

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    print(f"📚 Personality Database: {db_path}")
    print(f"   Location: {Path(db_path).absolute()}")
    print(f"   Size: {Path(db_path).stat().st_size / 1024:.1f} KB")
    if character_id:
        print(f"   Filter: {character_id} only")
    else:
        print(f"   Filter: All characters")
    print("=" * 80)

    # Show all characters in database
    cursor = db.execute("SELECT DISTINCT character_id FROM personality_traits")
    trait_chars = [row[0] for row in cursor.fetchall()]
    cursor = db.execute("SELECT DISTINCT character_id FROM memories")
    memory_chars = [row[0] for row in cursor.fetchall()]
    all_chars = sorted(set(trait_chars + memory_chars))

    if all_chars:
        print(f"\n🎭 CHARACTERS IN DATABASE: {', '.join(all_chars)}")
        print("-" * 80)

    # Build WHERE clause for character filtering
    where_char = f"WHERE character_id = '{character_id}'" if character_id else ""
    where_char_and = f"WHERE character_id = '{character_id}' AND" if character_id else "WHERE"

    # 1. Personality Traits
    print("\n🧠 PERSONALITY TRAITS")
    print("-" * 80)
    cursor = db.execute(f"""
        SELECT character_id, trait_name, trait_value, confidence, last_updated, context
        FROM personality_traits
        {where_char}
        ORDER BY character_id, last_updated DESC
    """)

    traits = cursor.fetchall()
    if traits:
        current_char = None
        for row in traits:
            if row['character_id'] != current_char:
                current_char = row['character_id']
                if not character_id:  # Only show character header if viewing all
                    print(f"\n  [{current_char}]")
            print(f"    {row['trait_name'].upper()}: {row['trait_value']}")
            print(f"      Confidence: {row['confidence']:.1%} | Updated: {format_timestamp(row['last_updated'])}")
            print(f"      Context: {row['context']}")
    else:
        print("  (No traits recorded yet)")

    # 2. Memories
    print("\n\n📝 MEMORIES (Most Recent First)")
    print("-" * 80)
    cursor = db.execute(f"""
        SELECT character_id, memory_type, description, emotional_impact, location, actor, timestamp, context
        FROM memories
        {where_char}
        ORDER BY character_id, timestamp DESC
        LIMIT 20
    """)

    memories = cursor.fetchall()
    if memories:
        current_char = None
        for row in memories:
            if row['character_id'] != current_char:
                current_char = row['character_id']
                if not character_id:
                    print(f"\n  [{current_char}]")

            impact = row['emotional_impact']
            emoji = "💔" if impact < -0.5 else "😊" if impact > 0.5 else "📌"
            impact_str = f"{impact:+.1f}"

            char_prefix = "    " if not character_id else "  "
            print(f"\n{char_prefix}{emoji} [{row['memory_type'].upper()}] {row['description']}")
            print(f"{char_prefix}  Impact: {impact_str} | Location: {row['location']} | Actor: {row['actor']}")
            print(f"{char_prefix}  Time: {format_timestamp(row['timestamp'])}")
            if row['context']:
                try:
                    ctx = json.loads(row['context'])
                    if ctx:
                        print(f"{char_prefix}  Context: {ctx}")
                except:
                    pass
    else:
        print("  (No memories recorded yet)")

    # 3. Learned Strategies
    print("\n\n🎯 LEARNED STRATEGIES (By Confidence)")
    print("-" * 80)
    cursor = db.execute(f"""
        SELECT character_id, situation, strategy, success_count, failure_count, confidence, last_used
        FROM learned_strategies
        {where_char}
        ORDER BY character_id, confidence DESC, success_count DESC
    """)

    strategies = cursor.fetchall()
    if strategies:
        for row in strategies:
            total = row['success_count'] + row['failure_count']
            conf = row['confidence'] or 0.0
            emoji = "✅" if conf > 0.6 else "❌" if conf < 0.4 else "🔶"

            print(f"\n  {emoji} {row['situation']} → {row['strategy']}")
            print(f"    Win/Loss: {row['success_count']}W - {row['failure_count']}L ({total} total)")
            print(f"    Confidence: {conf:.1%}")
            if row['last_used']:
                print(f"    Last used: {format_timestamp(row['last_used'])}")
    else:
        print("  (No strategies learned yet)")

    # 4. Prompt Injections
    print("\n\n💉 PROMPT INJECTIONS (Active)")
    print("-" * 80)
    cursor = db.execute(f"""
        SELECT character_id, agent_name, priority, content, created_at, reason
        FROM prompt_injections
        {where_char_and} active = 1
        ORDER BY character_id, priority DESC
    """)

    injections = cursor.fetchall()
    if injections:
        for row in injections:
            print(f"\n  [{row['agent_name'].upper()}] Priority {row['priority']}")
            print(f"    Content: {row['content']}")
            print(f"    Reason: {row['reason']}")
            print(f"    Created: {format_timestamp(row['created_at'])}")
    else:
        print("  (No active prompt injections)")

    # 5. Session Reflections
    print("\n\n📖 SESSION REFLECTIONS")
    print("-" * 80)
    cursor = db.execute(f"""
        SELECT session_id, character_id, start_time, end_time, reflection, stats
        FROM session_reflections
        {where_char}
        ORDER BY character_id, start_time DESC
        LIMIT 5
    """)

    sessions = cursor.fetchall()
    if sessions:
        for row in sessions:
            duration = row['end_time'] - row['start_time']
            duration_min = duration // 60

            print(f"\n  Session: {row['session_id']}")
            print(f"    Duration: {duration_min} minutes")
            print(f"    Started: {format_timestamp(row['start_time'])}")
            print(f"    Ended: {format_timestamp(row['end_time'])}")

            try:
                stats = json.loads(row['stats'])
                print(f"    Stats: {stats}")
            except:
                pass

            print(f"    Reflection: \"{row['reflection']}\"")
    else:
        print("  (No session reflections yet)")

    # Summary Stats
    print("\n\n📊 SUMMARY")
    print("-" * 80)
    print(f"  Traits: {len(traits)}")
    print(f"  Memories: {len(memories)}")
    print(f"  Strategies: {len(strategies)}")
    print(f"  Prompt Injections: {len(injections)}")
    print(f"  Sessions: {len(sessions)}")
    print("=" * 80)

    db.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "gap_personality.db"
    character_id = sys.argv[2] if len(sys.argv) > 2 else None
    view_personality(db_path, character_id)
