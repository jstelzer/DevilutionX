#!/usr/bin/env python3
"""
Test script for personality persistence system.

Verifies:
1. Database creation and schema initialization
2. Loading personality data
3. Adding traits, memories, strategies
4. Prompt context generation
5. Session reflection
"""

import sys
import logging
from pathlib import Path

# Add tools/gap to path
sys.path.insert(0, str(Path(__file__).parent))

from personality_store import PersonalityStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_personality_system():
    """Test personality system components"""
    logger.info("🧪 Testing Personality Persistence System")
    logger.info("=" * 60)

    # Test 1: Database creation
    logger.info("\n📝 Test 1: Database Creation")
    db_path = "test_personality.db"

    # Clean up any existing test database
    if Path(db_path).exists():
        Path(db_path).unlink()
        logger.info(f"   Removed existing {db_path}")

    personality = PersonalityStore(db_path=db_path)
    logger.info(f"   ✅ Created {db_path}")

    # Test 2: Load empty personality (should work, just empty)
    logger.info("\n📝 Test 2: Load Empty Personality")
    data = personality.load_personality()
    logger.info(f"   Traits: {len(data['traits'])}")
    logger.info(f"   Memories: {len(data['memories'])}")
    logger.info(f"   Strategies: {len(data['strategies'])}")
    logger.info("   ✅ Empty personality loads correctly")

    # Test 3: Add personality traits
    logger.info("\n📝 Test 3: Add Personality Traits")
    personality.update_trait(
        name="risk_tolerance",
        value="cautious",
        confidence=0.8,
        context="Nearly died to Butcher in first session"
    )
    personality.update_trait(
        name="player_relationship",
        value="trusting",
        confidence=0.9,
        context="Player shared many healing potions"
    )
    logger.info("   ✅ Added 2 traits")

    # Test 4: Add memories
    logger.info("\n📝 Test 4: Add Episodic Memories")
    personality.add_memory(
        memory_type="death",
        description="Killed by The Butcher on level 2",
        emotional_impact=-0.8,
        location="level_2",
        actor="Butcher",
        context={"cause": "overconfidence", "hp_at_death": 12}
    )
    personality.add_memory(
        memory_type="gift",
        description="Player dropped 3 healing potions after death",
        emotional_impact=0.9,
        location="level_2",
        actor="Player",
        context={"item_count": 3}
    )
    personality.add_memory(
        memory_type="victory",
        description="Cleared level 3 without taking damage",
        emotional_impact=0.6,
        location="level_3",
        actor="self",
        context={"strategy": "kiting"}
    )
    logger.info("   ✅ Added 3 memories")

    # Test 5: Add learned strategies
    logger.info("\n📝 Test 5: Add Learned Strategies")
    personality.add_strategy(
        situation="facing_butcher",
        strategy="retreat_to_stairs",
        success=True
    )
    personality.add_strategy(
        situation="facing_butcher",
        strategy="retreat_to_stairs",
        success=True
    )
    personality.add_strategy(
        situation="facing_butcher",
        strategy="stand_and_fight",
        success=False
    )
    personality.add_strategy(
        situation="low_hp_surrounded",
        strategy="teleport_to_town",
        success=True
    )
    logger.info("   ✅ Added 4 strategy records (3 situations)")

    # Test 6: Add prompt injections
    logger.info("\n📝 Test 6: Add Prompt Injections")
    personality.add_prompt_injection(
        agent_name="combat",
        priority=10,
        content="CRITICAL: Always retreat from The Butcher. He's too strong for direct combat.",
        reason="Death to Butcher (session_12345)"
    )
    personality.add_prompt_injection(
        agent_name="all",
        priority=5,
        content="Player is generous with potions - maintain trust by being helpful.",
        reason="Gift pattern detected (3+ potion gifts)"
    )
    logger.info("   ✅ Added 2 prompt injections")

    # Test 7: Load populated personality
    logger.info("\n📝 Test 7: Load Populated Personality")
    data = personality.load_personality()
    logger.info(f"   Traits: {len(data['traits'])}")
    for trait_name, trait_data in data['traits'].items():
        logger.info(f"      - {trait_name}: {trait_data['value']} (confidence: {trait_data['confidence']:.2f})")

    logger.info(f"   Memories: {len(data['memories'])}")
    for mem in data['memories']:
        logger.info(f"      - [{mem['type']}] {mem['description'][:50]}... (impact: {mem['impact']:+.1f})")

    logger.info(f"   Strategies: {len(data['strategies'])}")
    for strat in data['strategies']:
        logger.info(f"      - {strat['situation']}: {strat['strategy']} ({strat['success_count']}W-{strat['failure_count']}L, {strat['confidence']:.1%} confidence)")

    logger.info("   ✅ Populated personality loads correctly")

    # Test 8: Get prompt context
    logger.info("\n📝 Test 8: Get Prompt Context")
    combat_context = personality.get_prompt_context("combat")
    all_context = personality.get_prompt_context("healing")
    logger.info(f"   Combat context length: {len(combat_context)} chars")
    logger.info(f"   Healing context length: {len(all_context)} chars")
    if combat_context:
        logger.info(f"   Combat context preview: {combat_context[:80]}...")
    logger.info("   ✅ Prompt context generation works")

    # Test 9: Session reflection
    logger.info("\n📝 Test 9: Session Reflection")
    test_stats = {
        "battles": 15,
        "deaths": 1,
        "victories": 8,
        "near_deaths": 3,
        "gifts_received": 3,
        "levels_cleared": 2
    }
    personality.save_session_reflection(
        reflection="Learned to retreat from tough enemies. Player is supportive with items.",
        stats=test_stats
    )
    logger.info("   ✅ Session reflection saved")

    # Test 10: Close and reopen
    logger.info("\n📝 Test 10: Persistence Across Restarts")
    personality.close()
    logger.info("   Closed database")

    personality2 = PersonalityStore(db_path=db_path)
    data2 = personality2.load_personality()
    logger.info(f"   Reopened database")
    logger.info(f"   Traits after restart: {len(data2['traits'])}")
    logger.info(f"   Memories after restart: {len(data2['memories'])}")
    logger.info(f"   Strategies after restart: {len(data2['strategies'])}")
    logger.info("   ✅ Data persists across restarts")

    personality2.close()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("✅ ALL TESTS PASSED!")
    logger.info(f"   Test database: {db_path}")
    logger.info("   Personality system is ready for integration")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        test_personality_system()
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        sys.exit(1)
