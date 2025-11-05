-- Personality Persistence Schema
-- Enables companion AI to remember experiences, learn strategies, and evolve personality across sessions
-- CHARACTER-SPECIFIC: Each companion character (Rogue_5, Warrior_3, etc.) has separate memories/traits

-- Personality traits that evolve over time
CREATE TABLE IF NOT EXISTS personality_traits (
    character_id TEXT NOT NULL,
    trait_name TEXT NOT NULL,
    trait_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    last_updated INTEGER NOT NULL,
    context TEXT,
    session_id TEXT,
    PRIMARY KEY (character_id, trait_name)
);

-- Episodic memories (significant events)
CREATE TABLE IF NOT EXISTS memories (
    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    session_id TEXT,
    memory_type TEXT NOT NULL,
    description TEXT NOT NULL,
    emotional_impact REAL,
    location TEXT,
    actor TEXT,
    context TEXT
);

-- Learned strategies (tactical knowledge)
CREATE TABLE IF NOT EXISTS learned_strategies (
    strategy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL,
    situation TEXT NOT NULL,
    strategy TEXT NOT NULL,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used INTEGER,
    confidence REAL
);

-- Prompt injections (context for agents)
CREATE TABLE IF NOT EXISTS prompt_injections (
    injection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    priority INTEGER NOT NULL,
    content TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at INTEGER NOT NULL,
    reason TEXT
);

-- Session reflections (end-of-session summaries)
CREATE TABLE IF NOT EXISTS session_reflections (
    session_id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    start_time INTEGER NOT NULL,
    end_time INTEGER NOT NULL,
    reflection TEXT,
    stats TEXT,
    key_learnings TEXT
);

-- Indexes for common queries (character-scoped)
CREATE INDEX IF NOT EXISTS idx_memories_character ON memories(character_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(character_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_strategies_character ON learned_strategies(character_id, situation);
CREATE INDEX IF NOT EXISTS idx_injections_character ON prompt_injections(character_id, agent_name, active, priority DESC);
CREATE INDEX IF NOT EXISTS idx_traits_character ON personality_traits(character_id);
CREATE INDEX IF NOT EXISTS idx_reflections_character ON session_reflections(character_id, start_time DESC);
