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

## Phase 3: Actor Model Convergence (Week 1 ✅ COMPLETE)
*Unify Players and Monsters under common Actor interface*

### 3.1 Actor Abstraction

```cpp
// Source/actor/actor.h
class Actor {
public:
    virtual ActorId id() const = 0;
    virtual Point position() const = 0;
    virtual bool isAlive() const = 0;
    
    // Commands (thin façade ove\]---r existing systems)
    virtual void moveTo(Point target) = 0;
    virtual void attack(ActorId target) = 0;
    virtual void cast(SpellId spell, Point target) = 0;
    virtual void useItem(ItemId item) = 0;
};

dclass PlayerActor : public Actor {
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

#### Milestone C2: Monster Read-Only (Week 2)
- [ ] Implement MonsterActor with getters only
- [ ] Unify GAP state publishing (monsters + players)
- [ ] Improve LLM context with full actor visibility

#### Milestone C3: Actor Store (Week 3)
- [ ] Create unified ActorStore registry
- [ ] Support ActorId lookups across types
- [ ] Move shared utilities to Actor level

#### Milestone C4: Internal Migration (Week 4)
- [ ] Convert threat calculation to Actor API
- [ ] Convert pathfinding to Actor API
- [ ] Convert vision/LOS to Actor API

### 3.3 Benefits
- **Unified control** - Any actor controllable by any seat
- **Code reuse** - Shared logic for all entities
- **Future flexibility** - Easy to add new actor types
- **Clean architecture** - Single source of truth for entities

---

## Phase 4: Production Features (4-6 weeks)
*Polish for real gameplay experience*

### 4.1 Companion Intelligence

#### Advanced Combat AI
- [ ] Threat prioritization matrix
- [ ] Formation keeping algorithms  
- [ ] Combo coordination with player
- [ ] Spell rotation optimization
- [ ] Kiting and positioning tactics

#### Loot & Inventory Management
- [ ] Item evaluation heuristics
- [ ] Auto-equip better gear
- [ ] Smart potion management
- [ ] Gold/item sharing protocols

#### Communication
- [ ] Contextual battle callouts
- [ ] Strategy suggestions
- [ ] Quest commentary
- [ ] Personality system

### 4.2 Quality of Life

#### Configuration
- [ ] Companion personality presets
- [ ] Behavior tuning (aggressive/defensive/balanced)
- [ ] Model selection UI
- [ ] Performance profiles

#### Persistence
- [ ] Save/load companion state
- [ ] Experience/progression tracking
- [ ] Companion-specific achievements
- [ ] Statistics and analytics

### 4.3 Multiplayer Polish
- [ ] Companion spectator mode
- [ ] Multi-companion coordination
- [ ] PvP companion arenas
- [ ] Companion trading/sharing

### 4.4 Performance & Reliability
- [ ] Connection resilience (reconnect/fallback)
- [ ] State delta compression
- [ ] Adaptive quality (skip frames under load)
- [ ] Profiling and optimization

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
