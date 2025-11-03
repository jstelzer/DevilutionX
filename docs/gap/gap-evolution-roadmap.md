# GAP Evolution Roadmap: From POC to Production AI Companions

## Executive Summary

This document outlines the transformation of DevilutionX's GAP (Game Agent Protocol) from its current proof-of-concept state to a production-ready system where AI companions are first-class citizens alongside human players. The roadmap follows a pragmatic, incremental approach that maintains determinism, network compatibility, and enables continuous shipping.

**Current State**: Working LLM-controlled companion with combat working correctly after Phase 1 architecture fix. Ready for Phase 2 clean abstractions.

**Target State**: AI companions as full peers to human players, with clean entity control abstractions supporting 1-3+ AI players in cooperative gameplay.


---

## Phase 1: Emergency Architecture Fix ✅ COMPLETE (Sept 2025)
*Fixed the critical command routing bug - companion now attacks and moves correctly*

### 1.1 Problem Analysis ✅ COMPLETE
- **Issue**: `NetSendCmdLoc(companion_id, ...)` routes to main player instead of companion
- **Root Cause**: GAP evolved from single-player control without updating network layer
- **Impact**: All companion actions execute on wrong entity, making combat/navigation unusable

### 1.2 Solution Implemented ✅
Created network command isolation layer (`gap_network.h/cpp`) with:
- `NetSendCmdLocForPlayer()` - Routes location-based commands to correct player
- `NetSendCmdParam1ForPlayer()` - Routes parameter-based commands to correct player
- `ExecuteDirectMove()` - Direct movement execution for companions
- `ExecuteDirectAttack()` - Direct combat execution for companions (fixed with `ACTION_ATTACKMON`)
- `ExecuteDirectInteract()` - Direct object interaction for companions


Key fixes:
- Commands now execute on companion's position, not main player's
- Attack action type corrected from `ACTION_ATTACK` to `ACTION_ATTACKMON`
- Attacks allowed while walking (not just `PM_STAND` state)
- Proper attack initialization with direction, animation, and range checking

### 1.3 Deliverables ✅
- ✅ Fixed command routing in `Source/gap/gap_network.cpp` and `gap_intent.cpp`
- ✅ Added player ID validation in network layer
- ✅ Tested companion actions execute on correct player
- ✅ Verified multiplayer synchronization

### 1.4 Success Criteria ✅
- ✅ Companion attacks target from companion position
- ✅ Movement commands affect companion, not main player
- ✅ Chat messages show companion name correctly
- ✅ No multiplayer desync
- ✅ Companion executes attacks on correct targets
- ✅ Both melee and ranged attacks supported

---

## Phase 2: Bot Player Seat Architecture ✅ COMPLETE (Sept 2025)
*Transform companions into proper game entities with clean control interfaces*

### 2.1 Core Abstraction: Seat System

```cpp
// Source/seat/seat.h
class Seat {
public:
    virtual int playerIndex() const = 0;
    virtual void gatherIntents(std::vector<Intent>& out, uint64_t tick) = 0;
};

class HumanSeat : public Seat {
    // Wraps keyboard/mouse input -> intents
};

class CompanionSeat : public Seat {
    // Wraps GAP protocol -> intents
    void enqueue(const Intent& intent);
private:
    IntentQueue queue;
    RateLimiter limiter;
    SurvivalReflexes reflexes;
};
```


### 2.2 Intent Pipeline

```
Input Sources           Intent Layer              Engine Actions
─────────────          ──────────────            ───────────────
Keyboard/Mouse    ───► HumanSeat      ───►┐
                                           ├──► ApplyIntents() ───► NetSendCmd*()
GAP Protocol      ───► CompanionSeat  ───►┘
```

### 2.3 Implementation Steps ✅ COMPLETE

#### Week 1: Core Infrastructure ✅
- ✅ Created `Source/seat/` directory structure
- ✅ Implemented base Seat interface with Intent abstraction
- ✅ Created Intent types (Move, Attack, Interact, UseItem, Cast, Chat) and queue system
- ✅ Added SeatManager with intent execution pipeline

#### Week 2: HumanSeat Integration ✅
- ✅ Wrapped existing input handling in HumanSeat
- ✅ Achieved parity - game works identically with HumanSeat
- ✅ Added seat management to game loop with early-exit preservation

#### Week 3: CompanionSeat Implementation ✅
- ✅ Implemented CompanionSeat with rate limiting and survival reflexes  
- ✅ Wired GAP adapter bridge to CompanionSeat
- ✅ Added intent enqueueing and threat assessment
- ✅ Tested companion follows and fights through seat system

### 2.4 Critical Design Rules
1. **Never mutate state directly** - Always use NetSendCmd* 
2. **Host-only companions** - Only host generates companion intents
3. **Deterministic execution** - No random in intent path
4. **Rate limiting** - Max 5 intents/tick, 10/second
5. **UI isolation** - Companion never steals focus/camera


### 2.5 Deliverables ✅ COMPLETE
- ✅ Seat abstraction layer (`Source/seat/seat.h`, `seat_manager.cpp`)
- ✅ Intent queue with rate limiting and safety measures
- ✅ HumanSeat maintaining current behavior with intent generation
- ✅ CompanionSeat processing GAP intents with threat assessment
- ✅ Integration working in both single-player and multiplayer modes

### 2.6 Key Architectural Lessons Learned
**Chat System Architecture**: Chat intents are global broadcast events, not player-specific actions that require routing. Critical fix: prevent AI response loops by filtering AI messages (`[GAP AI]` prefix) in `ProcessChatMessage()` to stop the AI from responding to itself.

**Implementation Details**:
- Chat intents handled at GAP protocol level (`HandleChatIntent()` in `gap_core.cpp`)  
- Global broadcasts bypass seat system entirely - correct architectural approach
- AI messages filtered out of chat processing pipeline to prevent infinite loops
- Clean separation: Player messages → LLM, AI responses → display only

---

## Phase 3: Actor Model Convergence ✅ COMPLETE (Sept 2025)
*Unify Players and Monsters under common Actor interface*

### 3.1 Actor Abstraction

```cpp
// Source/actor/actor.h
class Actor {
public:
    virtual ActorId id() const = 0;
    virtual Point position() const = 0;
    virtual bool isAlive() const = 0;
    
    // Commands (thin facade over existing systems)
    virtual void moveTo(Point target) = 0;
    virtual void attack(ActorId target) = 0;
    virtual void cast(SpellId spell, Point target) = 0;
    virtual void useItem(ItemId item) = 0;
};

class PlayerActor : public Actor {
    int pnum;  // Wraps existing PlayerStruct
};

class MonsterActor : public Actor {
    int midx;  // Wraps existing MonsterStruct
};
```

### 3.2 Migration Milestones

#### Milestone C1: Player Actor Façade ✅ COMPLETE
- ✅ Implemented PlayerActor wrapping PlayerStruct (`Source/actor/player_actor.h/cpp`)
- ✅ Routed companion commands through Actor interface with proper network calls
- ✅ No behavior change - pure refactor maintaining full compatibility
- ✅ ActorStore for unified entity lookups (`Source/actor/actor_store.h/cpp`)
- ✅ Actor base interface with distance calculations and type system (`Source/actor/actor.h/cpp`)
- ✅ Integrated with GAP state extraction demonstrating Actor usage
- ✅ ActorId system for collision-free entity identification across types

#### Milestone C2: Monster Read-Only ✅ COMPLETE  
- ✅ Implemented MonsterActor with getters only (`Source/actor/monster_actor.h/cpp`)
- ✅ Unified GAP state publishing (monsters + players through Actor interface)
- ✅ ActorStore monster management with automatic refresh based on ActiveMonsters
- ✅ Consistent state extraction patterns abstracting game's non-ECS architecture

### 3.2.1 Why MonsterActor? Architectural Decision Rationale

**The Problem**: DevilutionX doesn't use an Entity Component System (ECS). Game state is scattered across multiple systems making GAP state extraction complex and error-prone:

```cpp
// Before: Manual field extraction in gap_state.cpp
for (size_t i = 0; i < ActiveMonsterCount; i++) {
    const auto& monster = Monsters[ActiveMonsters[i]];
    Point monsterPos = monster.position.tile;          // Manual field access
    monsters_json << "\"hp\":" << monster.hitPoints;   // No consistency with Player
    monsters_json << "\"hp_max\":" << monster.maxHitPoints; // Fixed-point conversions scattered
    // ... repeat for every field, different patterns than Player extraction
}
```

**The Solution**: MonsterActor provides a **consistent state publishing layer** that:

1. **Abstracts scattered data structures** - Hides `ActiveMonsters[]` indirection and manual field access
2. **Unified interface with PlayerActor** - Same methods, same patterns, same JSON structure  
3. **Single source of truth** - All monster data access goes through one clean interface
4. **Easier maintenance** - Add new monster properties in one place, not scattered across GAP code
5. **Foundation for expansion** - Items, Objects, NPCs can follow same Actor pattern

```cpp
// After: Clean, consistent interface
store.ForEachActiveMonster([&](const MonsterActor& actor) {
    monsters_json << actor.ToJson(); // Consistent with PlayerActor patterns
});
```

**This isn't about control** - it's about creating a **proper entity abstraction layer** for GAP that works with the game's existing non-ECS architecture without fighting against it.


#### Milestone C3: Actor Store ✅ COMPLETE
- ✅ Created unified ActorStore registry with player/monster management
- ✅ ActorId lookups across types with collision-free ID system
- ✅ Periodic refresh system for dynamic monster spawning/death
- ✅ Iteration patterns (`ForEachActivePlayer`, `ForEachActiveMonster`)

#### Critical Integration Fix ✅ COMPLETE
**Problem**: Seat system broke companion loading timing - CompanionSeat registered at startup but companion loaded at runtime.

**Solution**: Dynamic seat registration in `HandleHello()` when AI actually connects:
```cpp
// Register CompanionSeat for actual companion slot when companion connects
if (requested_slot != MyPlayerId) {
    auto& seatManager = devilution::SeatManager::Instance();
    seatManager.UnregisterSeat(requested_slot);
    auto companionSeat = std::make_unique<devilution::CompanionSeat>(requested_slot);
    seatManager.RegisterSeat(std::move(companionSeat));
}
```

✅ **Companion now works as distinct entity** - No more input control conflicts

### 3.3 Benefits
- **Unified control** - Any actor controllable by any seat
- **Code reuse** - Shared logic for all entities
- **Future flexibility** - Easy to add new actor types
- **Clean architecture** - Single source of truth for entities

---

## Phase 4: Incremental Production Polish (6-8 weeks)
*From functional companion to intelligent gameplay partner*

### 4.1 UI/UX: Companion as Real Player (Week 1-2)
*Make companions feel like genuine party members*

#### Core Visibility Features
- [ ] **Health Bar Display**: Companion health/mana bars visible on mouse-over (like monsters)
- [ ] **Player Panel Integration**: Companion appears in party UI with portrait, HP/MP bars
- [ ] **Status Indicators**: Visual indicators for companion state (fighting, following, looting, casting)
- [ ] **Damage Numbers**: Companion damage appears over targets (like player damage)
- [ ] **Nameplate Styling**: Distinctive companion nameplate color/styling (friendly blue vs enemy red)

#### Interactive Features  
- [ ] **Healing Support**: Player healing spells/potions affect companion
- [ ] **Buff/Debuff Visibility**: Companion status effects visible in UI
- [ ] **Equipment Display**: View companion gear when inspecting
- [ ] **Shared UI Elements**: Companion appears in relevant game dialogs (resurrection, etc.)

**Success Criteria**: Companion feels like a real party member, not an NPC

### 4.2 Enhanced Game State (Week 3)
*Give LLM complete situational awareness*

#### GAP Protocol Extensions
- [ ] **Detailed Spell State**: Available spells, cooldowns, mana costs, learned/unlearned
- [ ] **Full Inventory State**: All items with stats, equipped gear, item comparisons
- [ ] **Belt/Potion State**: Current potions, quantities, auto-use preferences
- [ ] **NPC/Object State**: Interactive NPCs, doors, chests, shrines with context
- [ ] **Economic State**: Gold, repair costs, vendor prices, item values

#### Environmental Awareness
- [ ] **Level Context**: Current area, quest objectives, previously visited areas
- [ ] **Danger Assessment**: Monster threat levels, environmental hazards
- [ ] **Opportunity Recognition**: Valuable items, beneficial shrines, tactical positions

**Success Criteria**: LLM has complete game state for intelligent decision-making

### 4.3 Combat Intelligence (Week 4-5)
*Transform basic attack-follow into tactical combat*

#### Smart Combat Decisions
- [ ] **Threat Prioritization**: Attack low-HP enemies first, prioritize dangerous casters
- [ ] **Formation Tactics**: Stay in healing range vs aggressive flanking based on situation
- [ ] **Target Switching**: Abandon tough enemies when player is overwhelmed
- [ ] **Spell Usage**: Cast appropriate spells based on situation (AOE for groups, single-target for elites)
- [ ] **Resource Management**: Use potions intelligently, conserve mana for important spells

#### Defensive Behaviors
- [ ] **Emergency Retreat**: Fall back when low health, seek healing
- [ ] **Player Support**: Prioritize helping player over personal combat
- [ ] **Crowd Control**: Use available CC spells to protect player
- [ ] **Positioning**: Avoid standing in fire, position for maximum effectiveness

**Success Criteria**: Companion makes smart tactical decisions that help rather than hinder

### 4.4 Inventory & Equipment Intelligence (Week 6)
*Autonomous gear management and item decisions*

#### Smart Looting
- [ ] **Item Evaluation**: Compare new items to current gear, consider upgrades
- [ ] **Duplicate Avoidance**: Don't pick up items player already has (uniques, quest items)
- [ ] **Value Optimization**: Drop low-value items when inventory full
- [ ] **Sharing Protocol**: Coordinate with player for item distribution

#### Equipment Management  
- [ ] **Auto-Equip Better Gear**: Automatically equip clear upgrades
- [ ] **Repair Decisions**: Repair gear when appropriate, prioritize important items
- [ ] **Potion Management**: Maintain appropriate potion supplies
- [ ] **Economic Decisions**: Buy/sell items intelligently at vendors

**Success Criteria**: Companion manages inventory without player micromanagement

### 4.5 Social & Communication (Week 7)
*Natural interaction and personality*

#### Contextual Communication
- [ ] **Combat Callouts**: "Behind you!", "Healing needed!", "Strong enemy ahead!"
- [ ] **Discovery Comments**: React to finding good items, dangerous areas
- [ ] **Strategic Suggestions**: "Should we rest in town?", "I need potions"
- [ ] **Personality Responses**: Consistent character voice and reactions

#### Communication Intelligence
- [ ] **Spam Prevention**: Limit frequency of callouts to avoid annoyance
- [ ] **Context Awareness**: Different communication styles for combat vs exploration vs town
- [ ] **Player Adaptation**: Learn player's communication preferences
- [ ] **Emergency Priority**: Important warnings override normal chat limits

**Success Criteria**: Companion communicates naturally and helpfully

### 4.6 Town & NPC Autonomy (Week 8)
*Full autonomous behavior in town environments*

#### NPC Interaction
- [ ] **Vendor Intelligence**: Buy supplies, sell junk items, repair equipment
- [ ] **Quest NPCs**: Interact with quest-givers appropriately
- [ ] **Service NPCs**: Use healers, identify items, gambling
- [ ] **Coordination**: Don't block player's NPC interactions

#### Town Behavior
- [ ] **Supply Management**: Maintain appropriate potions, arrows, keys
- [ ] **Economic Planning**: Balance spending on upgrades vs supplies
- [ ] **Preparation**: Get ready for next dungeon run (repairs, potions, spell preparation)
- [ ] **Following Logic**: Stay with player but don't crowd interfaces

**Success Criteria**: Companion handles town activities independently and intelligently

### 4.7 LLM Autonomy Milestones
*Progressive reduction of Python "helper code"*

#### Milestone 1 (Week 3): Enhanced Context
- Python provides rich game state, LLM makes all decisions
- Remove hardcoded survival reflexes, let LLM reason about danger

#### Milestone 2 (Week 5): Combat Reasoning  
- LLM handles all combat decisions without Python assistance
- Remove Python threat assessment, let LLM evaluate situations

#### Milestone 3 (Week 7): Full Autonomy
- Python becomes pure protocol bridge (GAP ↔ Ollama)
- All game logic reasoning handled by LLM
- Python only does JSON parsing and network communication

**Success Criteria**: LLM demonstrates sophisticated reasoning about complex game states

### Phase 4 Success Metrics

#### Technical Metrics
- [ ] Companion visible/interactive as real player
- [ ] <200ms average decision latency  
- [ ] Zero multiplayer desync issues
- [ ] Clean LLM reasoning without Python helpers

#### Gameplay Metrics
- [ ] Companion makes smart combat decisions
- [ ] Autonomous inventory/equipment management
- [ ] Natural communication without spam
- [ ] Effective town NPC interactions

#### Player Experience
- [ ] Companion feels like skilled human player
- [ ] Reduces player micromanagement burden
- [ ] Enhances rather than hinders gameplay
- [ ] Demonstrates clear personality and intelligence

---

## Phase 5: Future Horizons (Research)
*Long-term vision and experimental features*

### 5.1 Advanced AI Features
- **Multi-agent cooperation** - Multiple AI companions coordinating
- **Learning from player** - Adaptive behavior based on playstyle
- **Procedural personality** - Dynamic character development
- **Natural language commands** - Voice/text control of companions

### 5.2 Architectural Evolution
- **Headless game server** - Dedicated companion hosts
- **Cloud companions** - Remote AI processing
- **Modular AI backends** - Plugin different AI systems
- **Cross-game protocol** - GAP as industry standard

---

## Implementation Schedule

```
Week 1-2:   Phase 1 - Emergency Fix          [CRITICAL PATH]
Week 3-5:   Phase 2 - Bot Player Seat        [FOUNDATION]
Week 6-9:   Phase 3 - Actor Model            [ARCHITECTURE]
Week 10-15: Phase 4 - Production Features    [POLISH]
Ongoing:    Phase 5 - Research               [EXPLORATION]
```

## Risk Management

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Network desync | High | Strict host-only companion control |
| Performance regression | Medium | Profiling, frame skipping, quality modes |
| Save game corruption | High | Versioning, migration tools, backups |
| UI complexity | Medium | Hidden companion UI, focus locks |

### Project Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope creep | High | Strict phase boundaries, feature flags |
| Breaking changes | High | All changes behind ENABLE_GAP flag |
| Testing burden | Medium | Automated test suite per phase |
| Maintainability | Medium | Clear documentation, code reviews |

---

## Success Metrics

### Phase 1 Success ✅ COMPLETE
- ✅ Commands execute on correct player
- ✅ No multiplayer desync
- ✅ Chat shows proper names
- ✅ Attack actions work correctly (`ACTION_ATTACKMON`)
- ✅ Movement and combat from companion position
- ✅ Attacks work while walking
- ✅ Network command isolation layer implemented

### Phase 2 Success ✅ COMPLETE
- ✅ Seat abstraction working with unified intent pipeline
- ✅ Human gameplay unchanged (perfect parity with HumanSeat)
- ✅ Companion follows and fights through CompanionSeat
- ✅ Rate limiting prevents spam (5/tick, 10/second limits)
- ✅ Chat system architectural fix prevents AI response loops
- ✅ Global broadcasts handled correctly at protocol level
- ✅ Survival reflexes and threat assessment working

### Phase 3 Success
- ✅ Actor façade complete
- ✅ Unified state publishing
- ✅ Clean abstraction boundaries

### Phase 4 Success
- ✅ Smart combat decisions
- ✅ Inventory management working
- ✅ Personality system active
- ✅ Stable multiplayer experience

### Overall Success
- 🎯 1-3 AI companions playing cooperatively
- 🎯 Deterministic, synchronized multiplayer
- 🎯 <100ms latency for decisions
- 🎯 Positive player feedback
- 🎯 Clean, maintainable architecture

---

## Technical Debt Retirement

During implementation, address existing debt:
1. Replace custom JSON with nlohmann/json
2. Add comprehensive error handling
3. Create automated test suites
4. Document all protocols and APIs
5. Profile and optimize hot paths

---

## Conclusion

This roadmap transforms DevilutionX's experimental GAP system into a production-ready companion framework. By following this incremental approach, we can ship improvements continuously while building toward a clean, extensible architecture where AI companions are true peers to human players.

The key insight from IDEA.md is clear: **Path A (Bot Player Seat) → Path C (Actor Model)** provides the safest route forward, avoiding the complexity of Path B (pet/ally system) while achieving our goal of first-class AI companions.

Each phase delivers tangible value while setting up the next. Phase 1 unblocks immediate progress. Phase 2 establishes proper control abstractions. Phase 3 unifies the entity model. Phase 4 adds the polish needed for real gameplay. Phase 5 explores the future.

Let's build the future of cooperative AI gaming, one carefully planned step at a time.

### Ideas
### Determinism & Replay

**Invariant:** Companion actions must not introduce nondeterminism across SP/MP.


**Replay harness**
- Record `(tick, playerIndex, CMD_*, params)` to a ring buffer (host).
- Add `--replay=<file>` mode that re-injects commands and asserts:
  - same RNG seeds per level
  - same final checksums for: player pos, HP/mana, active monsters (id,hp,pos).

**Checksums**
- `level_crc = crc32(all player states || all active monster states)`
- Emit every N ticks; compare across host/client in MP test runs.

**CI smoke**
- Headless build + 30s replay on a known seed; ensure `level_crc` stability.


### State Delta Strategy

- **Keyed entities**: players by `pnum`, monsters by `midx`, objects by `oid`.
- Send full snapshot on connect or every `K` seconds; otherwise:
  - `{"type":"state_delta", "tick": T, "players":[...changed], "monsters":[...changed], "objects":[...changed]}`
- Drop outbound frames under backpressure (never stall the sim). Client acks last-applied tick.

### Multi-Companion Guardrails

- One `CompanionSeat` per `pnum`; host-only activation.
- SeatManager enforces unique `pnum` and denies duplicate registration.
- On disconnect: seats become inert but remain registered until level transition (avoids focus flicker).

# GAP v0.3 Delta

This augments v0.2 with minimal fields to unlock combat, inventory, and traversal.

## Intents (Agent → Game)

```json
{ "type":"intent", "data": { "cmd":"move_to",   "x":50, "y":55, "targetTick":12346 } }
{ "type":"intent", "data": { "cmd":"attack_id", "id":42 } }
{ "type":"intent", "data": { "cmd":"attack_pos","x":52, "y":47 } }
{ "type":"intent", "data": { "cmd":"cast",      "slot":1, "x":52, "y":47 } }
{ "type":"intent", "data": { "cmd":"pickup",    "id":16 } }
{ "type":"intent", "data": { "cmd":"use_potion","kind":"hp" } }    // or {"slot":0}
{ "type":"intent", "data": { "cmd":"interact",  "id":301 } }       // door/chest/stairs/portal
{ "type":"intent", "data": { "cmd":"say",       "text":"On me!" } }
{ "type":"intent", "data": { "cmd":"stop" } }

## State additions Game -> Agent

```
{
  "type":"state",
  "tick":12345,
  "data":{
    "player": {
      "id": 0,
      "hp":150,"hp_max":200,
      "mana":80,"mana_max":120,
      "pos":[50,45],"level":8,"in_town":false,
      "belt":[ {"t":"hp","n":2}, {"t":"mp","n":1}, null, null ],
      "spells": { "slot1":"Firebolt", "slot2":"Town Portal" }
    },
    "monsters":[
      {"id":42,"name":"Skeleton","pos":[52,47],
       "hp":45,"hp_max":60,"hp_percent":75,"armor":12,
       "is_alive":true,"is_minion":false,"distance":3}
    ],
    "objects":[
      {"id":301,"kind":"chest","pos":[49,44],"locked":false},
      {"id":302,"kind":"stairs_down","pos":[60,15]}
    ],
    "vision":{
      "light_radius":10,
      "player_pos":[50,45],
      "walkable_grid":[[true,false,true], [true,true,true], ...]
    }
  }
}
```


## Core Gameplay Feedback


### Current Observations

The companion follows, but rarely attacks.


When I mouse over the frame I see no health like I do for monsters. Is the game engine seeing the companion as an attackable player with health?


Can I heal the companion?


Spell slots, we need to teach it about them.

Inventory. Same issue.

- Available spells and their appropriate usage contexts
- Inventory space management and item prioritization  
- Equipment comparison and upgrade decisions
Consider adding detailed spell/inventory state to the GAP protocol. -->

Then there's the game in town. The companion should use the townsfolk to get supplies, repair gear, buy upgrades, etc.

- NPC interaction protocols in GAP
- Economic decision-making (what to buy/sell/repair)
- Coordination with player's town activities
This could be a separate Phase 4 milestone: "Town Management AI" -->

I would like the LLM to be able to reason about and do all of this.

Right now there's some python code in the MCP that 'helps'. in a perfect world the MCP would bootstrap the LLM and the LLM would handle things.


---

## Overall Strategic Feedback

### Roadmap Strengths

1. **Incremental Approach**: The phase-by-phase progression allows for continuous validation and course correction. Each phase delivers tangible value while building toward the larger vision.

2. **Technical Depth**: The document demonstrates deep understanding of both the legacy codebase constraints and modern architectural patterns. The Actor abstraction and Seat system are particularly well-designed.

3. **Production Mindset**: The emphasis on determinism, replay systems, rate limiting, and multiplayer stability shows mature game development thinking.

4. **Clear Success Criteria**: Each phase has well-defined deliverables and success metrics, making progress measurable.

### Suggested Additions/Refinements

1. **Phase 4 Prioritization**: Consider breaking Phase 4 into sub-phases based on impact:
   - 4a: Core Intelligence (combat + inventory)  
   - 4b: Communication & Personality
   - 4c: Advanced Features (town NPCs, multi-companion)

2. **Performance Benchmarking**: Add specific performance targets:
   - Max latency for AI decisions (currently <100ms is mentioned)
   - Memory usage limits for AI systems
   - Frame rate impact measurements

3. **Gradual LLM Autonomy**: Create a migration plan for reducing Python "helper code":
   - Phase 4.1: Enhanced GAP protocol with spell/inventory details
   - Phase 4.2: LLM reasoning about complex game states
   - Phase 4.3: Remove Python decision-making layer

4. **User Research Integration**: Consider adding user feedback loops:
   - Alpha testing with companion behavior tuning
   - Metrics collection on companion effectiveness
   - Player satisfaction surveys

### Risk Mitigation Suggestions

1. **LLM Reliability**: Add fallback behaviors for when LLM responses are malformed/delayed
2. **Configuration Management**: Create companion behavior profiles (conservative/balanced/aggressive) for different player preferences  
3. **Debugging Infrastructure**: Enhance the replay system with AI decision audit trails

This roadmap represents excellent planning for a complex technical and gameplay challenge. The foundation work (Phases 1-3) is solid, and the production features (Phase 4) address the real gameplay needs identified in your observations.
