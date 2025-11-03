# Multi-Agent Council Architecture for DevilutionX

**The Evolution**: From single LLM doing everything → Specialized agent council with orchestration

## Core Philosophy

"What if there were more than one dimension?"

Instead of one LLM trying to balance combat, survival, loot, and cooperation - we have a **council of specialist agents**, each expert in their domain, communicating at the seams with a clear hierarchy of trust and deference.

### Benefits

- **Prompt Isolation**: Each agent has 30-80 token prompts vs 400-600 token monolith
- **Parallel Execution**: We have clock cycles to spare - run agents concurrently
- **Clear Priorities**: Orchestrator enforces hierarchy (healing > combat > loot > exploration)
- **Extensibility**: Add new agents without touching existing ones
- **Debuggability**: See each agent's vote and why the orchestrator picked the winner
- **Model Flexibility**: Fast 3B models for simple agents, smarter 8B for complex ones

---

## Complete Agent Council

### Core Agents (Dungeon Active)

#### Combat Agent - "The Warrior"
```python
Prompt: """
You are the Combat specialist. Rate attack targets.

Monsters: {monsters}
Your HP: {hp}%
Your Position: {pos}

Output ONE line:
AT {id} {weight}

Weight (0.0-1.0):
- 1.0 = Low HP enemy, immediate threat
- 0.7 = Healthy enemy, moderate threat
- 0.3 = Distant enemy, low priority
- 0.0 = No viable targets
"""

State required: monsters, hp, pos
Output: {"AT 27": 0.85, "AT 47": 0.62, "NONE": 0.0}
Context: ~50 tokens
Speed: 100-200ms
Dormant when: in_town=True
Defers to: Healing (always), Stats (if leveling)
Model: qwen2.5:3b
```

#### Healing Agent - "The Medic"
```python
Prompt: """
You are the Healing specialist. Decide if healing is needed.

HP: {hp}%
Belt: {belt}  # "0:HEAL,1:MANA,2:HEAL,3:EMPTY"

Output ONE line:
USE {slot} {weight}  OR  NONE 0.0

Weight (0.0-1.0):
- 1.0 = HP < 20% (critical)
- 0.8 = HP 20-35% (urgent)
- 0.5 = HP 35-50% (recommended)
- 0.0 = HP > 60% (safe)
"""

State required: hp, belt_slots
Output: {"USE 0": 0.95} or {"NONE": 0.0}
Context: ~30 tokens
Speed: 50-100ms
Priority: HIGHEST (overrides all except death)
Defers to: Nothing
Model: qwen2.5:3b
```

#### Movement Agent - "The Scout"
```python
Prompt: """
You are the Movement specialist. Rate movement options.

Your Position: {me}
Player Position: {plyr}
Monsters: {monsters}  # "27@62,79 47@64,76"
Safe Tile: {safe}

Output ONE line:
MV {x} {y} {weight}

Weight (0.0-1.0):
- 1.0 = Near player, safe from monsters
- 0.7 = Tactical position for combat
- 0.3 = Exploration/loot position
"""

State required: me, player_pos, monsters, safe_zones
Output: {"MV 72 81": 0.8, "MV 75 80": 0.5}
Context: ~80 tokens
Speed: 100-200ms
Dormant when: Never (always need positioning)
Defers to: Combat (tactical), Healing (retreat)
Model: llama3.2:latest
```

#### Loot Agent - "The Treasure Hunter"
```python
Prompt: """
You are the Loot specialist. Rate item pickup priority.

Items on ground: {items}  # "71@35,19:gold 13@40,20:weapon"
Your Class: {class}
Inventory Free Slots: {free_slots}

Output ONE line:
PK {id} {weight}

Weight (0.0-1.0):
- 1.0 = Gold or class-relevant unique
- 0.7 = Useful equipment upgrade
- 0.5 = Potions/scrolls
- 0.3 = Vendor trash
- 0.0 = Not worth picking up
"""

State required: items, class, inventory_free_slots
Output: {"PK 71": 0.9, "PK 13": 0.3}
Context: ~40 tokens
Speed: 50-100ms
Dormant when: no_loot_nearby OR combat_active
Defers to: Combat, Healing, Inventory
Model: qwen2.5:3b
```

#### Inventory Agent - "The Quartermaster"
```python
Prompt: """
You are the Inventory specialist. Manage belt organization.

Belt: {belt}  # "0:HEAL,1:MANA,2:EMPTY,3:HEAL"
Inventory: {inv}
Goal: 2 health potions, 1 mana potion in belt

Output ONE line:
REORGANIZE {weight}  OR  NONE 0.0

Weight: 0.0-1.0 based on how badly belt needs fixing.
"""

State required: belt_slots, inventory
Output: {"REORGANIZE": 0.6} or {"NONE": 0.0}
Context: ~30 tokens
Speed: 50-100ms
Update frequency: Every 5-10 seconds (not every tick)
Dormant when: in_combat
Defers to: Combat, Healing
Model: qwen2.5:3b
```

---

### Situational Agents (Context-Dependent)

#### Town Agent - "The Merchant"
```python
Prompt: """
You are the Town specialist. Handle NPCs and commerce.

Location: Town
NPCs Available: Cain, Griswold, Pepin, Ogden
Gold: {gold}
Unidentified Items: {unid_count}
Inventory Status: {inv_status}

Output ONE line with highest priority action:
TALK Cain {weight}      # Identify items
TALK Griswold {weight}  # Buy/sell equipment
TALK Pepin {weight}     # Buy potions
PORTAL {weight}         # Return to dungeon

Weight: 0.0-1.0 based on urgency.
"""

State required: in_town, gold, unidentified_items, inventory
Output: {"TALK Cain": 0.9, "TALK Griswold": 0.7, "PORTAL": 0.2}
Context: ~60 tokens
Speed: 100-200ms
Dormant when: in_dungeon=True
Priority: LOW (only active in safe zone)
Responsibilities:
- Item identification (Cain)
- Selling junk loot (Griswold)
- Buying potions/scrolls (Pepin)
- Equipment upgrades (Griswold)
- Quest NPCs (Ogden for gossip)
Model: llama3.2:latest
```

#### Stats Agent - "The Trainer"
```python
Prompt: """
You are the Stats specialist. Allocate stat points on level up.

Level Up Available!
Class: {class}
Current Stats: STR={str} MAG={mag} DEX={dex} VIT={vit}
Build Goal: {build}  # "tank", "glass_cannon_mage", "archer", "hybrid"

Output ONE line:
STAT_STR {weight}
STAT_MAG {weight}
STAT_DEX {weight}
STAT_VIT {weight}

Weight based on build optimization.

Build guidelines:
- tank: Prioritize VIT, STR
- glass_cannon_mage: Prioritize MAG, minimal VIT
- archer: Prioritize DEX, some VIT
- hybrid: Balanced allocation
"""

State required: level_up_available, class, stats, build_goal
Output: {"STAT_MAG": 0.9, "STAT_VIT": 0.6, "STAT_STR": 0.3}
Context: ~50 tokens
Speed: 100-200ms
Dormant when: level_up_available=False
Priority: HIGH (pauses dungeon activity for character development)
Defers to: Nothing when active
Frequency: Rare (only on level up)
Model: llama3.2:latest
```

#### Spell Agent - "The Mage"
```python
Prompt: """
You are the Spell specialist for casters.

Spells Available: {spells}  # "FIREBALL:40mp, CHAIN_LIGHTNING:60mp"
Mana: {mp}%
Monsters: {monsters}

Output ONE line:
CAST FIREBALL {id} {weight}
CAST CHAIN_LIGHTNING {id} {weight}
MELEE {id} {weight}  # Staff melee to conserve mana

Weight (0.0-1.0):
- Consider mana efficiency
- Don't cast if MP < 30% (save for escape)
- Prefer high-damage spells when dangerous
- Use cheap spells for cleanup
"""

State required: spells, mp, monsters, class
Output: {"CAST FIREBALL 27": 0.8, "MELEE 47": 0.3}
Context: ~60 tokens
Speed: 100-200ms
Dormant when: class not in [Sorcerer, Mage] OR in_town
Defers to: Healing (don't blow mana if need to flee)
Cooperates with: Combat (spell vs melee), Movement (AOE positioning)
Model: llama3.2:latest
```

#### Exploration Agent - "The Cartographer"
```python
Prompt: """
You are the Exploration specialist. Guide dungeon navigation.

Explored Areas: {explored_tiles}
Quest Objectives: {objectives}
Unexplored Nearby: {unexplored}

Output ONE line:
MV {x} {y} {weight}  # Move to unexplored area

Weight (0.0-1.0):
- Quest objectives = 1.0
- Stairs/portals = 0.9
- Unexplored areas = 0.6
- Already explored = 0.0
"""

State required: explored_map, quest_objectives, current_pos
Output: {"MV 45 60": 0.8, "MV 50 70": 0.5}
Context: ~70 tokens
Speed: 200-300ms (can be slower, low priority)
Update frequency: Every 10-20 seconds
Dormant when: in_combat OR following_player_closely
Priority: LOWEST (exploration only when safe)
Model: qwen2.5:3b
```

---

### Meta-Agent (Influences All Others)

#### Danger Assessment Agent - "The Strategist"
```python
Prompt: """
You are the Danger Assessment specialist. Evaluate overall risk.

HP: {hp}%
Mana: {mp}%
Monsters Nearby: {monster_count}
Monster Types: {monster_types}  # "Skeleton(3), Zombie(1), Unique(1)"
Potions in Belt: {potion_count}
In Town: {in_town}

Output ONE line:
DANGER {level} RETREAT={bool} BOSS={bool} OVERWHELMED={bool}

Danger level (0.0-1.0):
- 0.0-0.2: SAFE (no threats, full resources)
- 0.3-0.5: CAUTIOUS (some threats, good resources)
- 0.6-0.8: DANGEROUS (many threats OR low resources)
- 0.9-1.0: CRITICAL (imminent death, must flee)

Flags:
- RETREAT: true if should return to town
- BOSS: true if unique/boss detected
- OVERWHELMED: true if 5+ monsters nearby
"""

State required: full_state
Output: {
    "danger_level": 0.7,
    "retreat_recommended": false,
    "boss_detected": true,
    "overwhelmed": false
}
Context: ~100 tokens
Speed: 150-250ms
Always active: True (runs every state update)
Used by: Orchestrator to weight all other decisions
Model: llama3.2:latest
```

---

### Future Agents (Not Yet Implemented)

#### Party Agent - "The Coordinator"
```python
Dormant when: single_player=True
Responsibilities:
- Monitor party member health
- Item sharing/trading
- Role coordination (tank/DPS/support)
- Communication (chat messages)
Model: llama3.2:latest
```

#### Quest Agent - "The Guide"
```python
Dormant when: no_active_quests
Responsibilities:
- Quest tracking
- Objective guidance
- NPC interaction for quest completion
Model: qwen2.5:3b
```

#### Resource Management Agent - "The Economist"
```python
Dormant when: in_combat OR in_dungeon
Responsibilities:
- Potion shopping strategy
- Gold management
- Scroll purchasing
- Long-term resource planning
Model: qwen2.5:3b
```

---

## Orchestrator Architecture

### Decision Tree

```python
class AgentOrchestrator:
    """
    The orchestrator receives DSL state from the game, distributes it to agents,
    collects their weighted recommendations, and picks the optimal action.
    """

    def __init__(self):
        # Core agents (always initialized)
        self.combat = CombatAgent(model="qwen2.5:3b")
        self.healing = HealingAgent(model="qwen2.5:3b")
        self.movement = MovementAgent(model="llama3.2:latest")
        self.loot = LootAgent(model="qwen2.5:3b")
        self.inventory = InventoryAgent(model="qwen2.5:3b")

        # Situational agents
        self.town = TownAgent(model="llama3.2:latest")
        self.stats = StatsAgent(model="llama3.2:latest")
        self.spell = SpellAgent(model="llama3.2:latest")
        self.exploration = ExplorationAgent(model="qwen2.5:3b")

        # Meta agent
        self.danger = DangerAssessmentAgent(model="llama3.2:latest")

        # Agent state tracking
        self.last_inventory_update = 0
        self.last_exploration_update = 0

    async def decide(self, state: GameState) -> str:
        """
        Main decision loop. Returns a DSL command string.

        Returns:
            str: DSL command like "AT 27", "MV 72 81", "USE 0", etc.
        """

        # Meta-agent always runs first to assess danger
        danger = await self.danger.evaluate(state)
        state.danger_level = danger.level  # Augment state with danger

        # Context switches
        if state.in_town:
            return await self._handle_town(state)

        if state.level_up_available:
            return await self._handle_level_up(state)

        # Standard dungeon decision
        return await self._handle_dungeon(state, danger)

    async def _handle_town(self, state: GameState) -> str:
        """Town mode - shopping, identification, preparation"""

        # Town agent evaluates NPCs and shopping
        town_action = await self.town.evaluate(state)

        # Inventory can reorganize in town (safe zone)
        if self.inventory.needs_reorganization(state):
            inv_action = await self.inventory.evaluate(state)
            if inv_action.weight > town_action.weight:
                return inv_action.command

        return town_action.command

    async def _handle_level_up(self, state: GameState) -> str:
        """Level up - stats agent takes over"""
        stats_action = await self.stats.evaluate(state)
        return stats_action.command

    async def _handle_dungeon(self, state: GameState, danger: DangerAssessment) -> str:
        """
        Main dungeon decision loop.

        Priority hierarchy:
        1. CRITICAL HEALING (HP < 25% or danger > 0.85)
        2. COMBAT (if monsters nearby and HP > 35%)
        3. SPELL (for casters with mana)
        4. HEALING (if HP < 90%)
        5. LOOT (if safe, danger < 0.4)
        6. MOVEMENT (always available as fallback)
        7. EXPLORATION (very safe, danger < 0.3)
        """

        # CRITICAL: Emergency healing override
        if state.hp < 25 or danger.level > 0.85:
            healing_action = await self.healing.evaluate(state)
            if healing_action.weight > 0.7:
                print(f"🚨 EMERGENCY HEALING: HP={state.hp}% Danger={danger.level:.2f}")
                return healing_action.command

        # Prepare parallel evaluations
        tasks = {}

        # Combat - evaluate if monsters nearby
        if state.monsters_nearby:
            tasks["combat"] = self.combat.evaluate(state)

            # Spell agent for casters
            if state.player_class in ["Sorcerer", "Mage"]:
                tasks["spell"] = self.spell.evaluate(state)

        # Healing - evaluate if HP < 90%
        if state.hp < 90:
            tasks["healing"] = self.healing.evaluate(state)

        # Movement - always evaluates
        tasks["movement"] = self.movement.evaluate(state)

        # Loot - only if safe
        if state.loot_nearby and danger.level < 0.5:
            tasks["loot"] = self.loot.evaluate(state)

        # Exploration - only if very safe
        current_time = time.time()
        if (danger.level < 0.3 and
            not state.monsters_nearby and
            current_time - self.last_exploration_update > 10.0):  # Throttle to 10s
            tasks["exploration"] = self.exploration.evaluate(state)
            self.last_exploration_update = current_time

        # Execute agents in parallel
        responses = {}
        try:
            results = await asyncio.gather(*tasks.values(), timeout=0.5)
            responses = dict(zip(tasks.keys(), results))
        except asyncio.TimeoutError:
            print("⚠️ Agent timeout - using partial responses")

        # Build candidates with base priorities
        candidates = []

        # Priority scoring: agent_weight * priority_multiplier * danger_modifier
        danger_modifier = 1.0 if danger.level < 0.5 else 0.5

        # HEALING (priority 10)
        if "healing" in responses and responses["healing"].weight > 0.5:
            score = responses["healing"].weight * 10 * danger_modifier
            candidates.append(("healing", responses["healing"], score))

        # COMBAT (priority 8)
        if "combat" in responses and state.hp > 35:
            score = responses["combat"].weight * 8 * danger_modifier
            candidates.append(("combat", responses["combat"], score))

        # SPELL (priority 8, competes with combat)
        if "spell" in responses and state.mp > 30:
            score = responses["spell"].weight * 8 * danger_modifier
            candidates.append(("spell", responses["spell"], score))

        # LOOT (priority 5)
        if "loot" in responses and danger.level < 0.4:
            score = responses["loot"].weight * 5 * danger_modifier
            candidates.append(("loot", responses["loot"], score))

        # MOVEMENT (priority 3 - fallback)
        if "movement" in responses:
            score = responses["movement"].weight * 3
            candidates.append(("movement", responses["movement"], score))

        # EXPLORATION (priority 1 - lowest)
        if "exploration" in responses:
            score = responses["exploration"].weight * 1
            candidates.append(("exploration", responses["exploration"], score))

        # Pick highest score
        if not candidates:
            # Fallback: stand still
            return "SAY Waiting..."

        best = max(candidates, key=lambda x: x[2])
        agent_name, action, score = best

        # Debug logging
        print(f"🎯 Decision: {agent_name} → {action.command} (score: {score:.2f})")
        print(f"   Danger: {danger.level:.2f} | HP: {state.hp}% | Monsters: {len(state.monsters)}")
        if len(candidates) > 1:
            print(f"   Alternatives: {[(c[0], c[2]) for c in sorted(candidates, key=lambda x: x[2], reverse=True)[1:3]]}")

        return action.command
```

---

## Agent Implementation Pattern

```python
class BaseAgent:
    """Base class for all specialist agents"""

    def __init__(self, model: str, ollama_url: str = "http://localhost:11434/api/generate"):
        self.model = model
        self.ollama_url = ollama_url

    async def evaluate(self, state: GameState) -> AgentResponse:
        """
        Evaluate state and return weighted recommendation.

        Returns:
            AgentResponse(command: str, weight: float, reasoning: str)
        """
        raise NotImplementedError

    async def query_llm(self, prompt: str) -> str:
        """Query Ollama with grammar constraints"""
        # Similar to existing dsl_agent.py implementation
        pass

class AgentResponse:
    """Response from an agent evaluation"""
    def __init__(self, command: str, weight: float, reasoning: str = ""):
        self.command = command  # DSL command: "AT 27", "MV 72 81", etc.
        self.weight = weight    # 0.0-1.0
        self.reasoning = reasoning  # Optional debug info
```

---

## Implementation Roadmap

### Phase 1: Proof of Concept (2-3 days)
- [ ] Create `tools/gap/agents/` directory structure
- [ ] Implement `BaseAgent` and `AgentResponse` classes
- [ ] Extract Combat agent from current `dsl_agent.py`
- [ ] Extract Healing agent (threshold logic + LLM)
- [ ] Extract Movement agent (player-following)
- [ ] Simple orchestrator (healing > combat > movement)
- [ ] Test with existing DSL protocol

### Phase 2: Expand Council (3-5 days)
- [ ] Add Loot agent
- [ ] Add Inventory agent
- [ ] Add Danger Assessment meta-agent
- [ ] Add Town agent with NPC interaction
- [ ] Tune weights and deference rules

### Phase 3: Advanced Agents (5-7 days)
- [ ] Add Stats agent for level-ups
- [ ] Add Spell agent for casters
- [ ] Add Exploration agent with map memory
- [ ] Implement agent dormancy system
- [ ] Add debug UI for agent voting visualization

### Phase 4: Optimization (2-3 days)
- [ ] Thread pool for parallel LLM calls
- [ ] Response caching for slow-changing state
- [ ] Model selection optimization per agent
- [ ] Performance profiling and tuning

---

## File Structure

```
tools/gap/
├── dsl_agent.py              # Old monolithic agent (deprecated)
├── orchestrator.py           # NEW: Main orchestrator
├── agents/
│   ├── __init__.py
│   ├── base.py              # BaseAgent, AgentResponse
│   ├── combat.py            # Combat specialist
│   ├── healing.py           # Healing specialist
│   ├── movement.py          # Movement specialist
│   ├── loot.py              # Loot specialist
│   ├── inventory.py         # Inventory specialist
│   ├── town.py              # Town specialist
│   ├── stats.py             # Stats specialist
│   ├── spell.py             # Spell specialist
│   ├── exploration.py       # Exploration specialist
│   └── danger.py            # Danger assessment meta-agent
├── dsl_parser.py            # DSL state parsing (unchanged)
├── chat_handler.py          # Chat thread (unchanged)
└── memory_store.py          # SQLite memory (unchanged)
```

---

## Integration with Existing System

**Minimal changes to C++ side:**
- DSL protocol stays the same
- Add belt/inventory info to state (planned anyway)
- Add level_up_available flag
- Add in_town flag

**Python agent evolution:**
```python
# OLD: dsl_agent.py
agent = DSLAgent(model="qwen2.5:3b")
agent.run()

# NEW: orchestrator.py
orchestrator = AgentOrchestrator()
orchestrator.run()
```

**Backwards compatible:** Can run old agent or new orchestrator with same game build.

---

## Success Metrics

Council system is successful if:
- ✅ Decisions 2x faster than monolithic agent (parallel execution)
- ✅ Companion survives longer (healing agent prevents deaths)
- ✅ Better combat effectiveness (combat agent focus)
- ✅ Efficient looting (loot agent specialization)
- ✅ Clear debug visibility (see all agent votes)
- ✅ Extensible (add new agents without changing orchestrator)

---

**Built for the friends who played Diablo with me and have since passed on.**

*"The council stands ready. Let's clear these dungeons together."*

🔥🤘💀
