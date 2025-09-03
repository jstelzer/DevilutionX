## Design Philosophy: From Tactical AI to Strategic AI

**Current State**: We have a reactive tactical AI that fights well but lacks strategic thinking.
**Goal**: Transform it into a strategic AI that understands Diablo's core gameplay loop.

The LLM has extensive Diablo knowledge - we need to unlock that strategic reasoning.

---

## Core Issues & Solutions

### 1. Map Exploration Problem
**Issue**: AI doesn't systematically explore levels or remember where it's been.

**Approach A: Enhanced Memory System**
```python
class DungeonMemory:
    def __init__(self):
        self.level_maps = {}  # level_num -> explored_tiles
        self.room_boundaries = {}  # detected room structures
        self.exploration_goals = []  # ordered list of unexplored areas
        self.completion_status = {}  # level_num -> completion_percentage
        self.visit_counts = {}  # track how often we visit each tile
        self.dead_ends = {}  # remember dead end locations
        self.monster_spawns = {}  # remember where monsters appeared
    
    def update_exploration(self, level, visible_tiles, cleared_tiles):
        """Update exploration data from GAP state"""
        if level not in self.level_maps:
            self.level_maps[level] = set()
        
        self.level_maps[level].update(visible_tiles)
        completion = len(cleared_tiles) / max(len(visible_tiles), 1) * 100
        self.completion_status[level] = completion
        
        # Find frontier tiles (explored but adjacent to unexplored)
        frontier = self._find_frontier_tiles(level, visible_tiles)
        self.exploration_goals = sorted(frontier, key=lambda pos: self._exploration_priority(pos))
    
    def _exploration_priority(self, pos):
        """Score tiles for exploration priority"""
        # Prefer unvisited areas, avoid frequently visited spots
        visit_penalty = self.visit_counts.get(pos, 0) * 10
        dead_end_penalty = 50 if pos in self.dead_ends else 0
        return -(visit_penalty + dead_end_penalty)  # negative for min-heap sorting
```

**Approach B: Exploration Heuristics**
```python
class ExplorationHeuristics:
    def __init__(self):
        self.wall_following_state = None
        self.room_graph = {}  # room_id -> {neighbors, center_pos, area}
        self.exploration_stack = []  # for backtracking
        
    def wall_follow_algorithm(self, current_pos, walkable_grid):
        """Classic wall-following: keep wall on right side"""
        # Find nearest wall, then follow it systematically
        # Ensures we don't miss any areas in complex layouts
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]  # right, down, left, up
        
        for direction in directions:
            wall_pos = (current_pos[0] + direction[0], current_pos[1] + direction[1])
            if not walkable_grid[wall_pos]:  # found wall
                # Follow wall perimeter while scanning inward
                return self._follow_wall_perimeter(current_pos, wall_pos, walkable_grid)
    
    def detect_room_structure(self, walkable_grid):
        """Use flood-fill to identify connected room areas"""
        rooms = []
        visited = set()
        
        for y in range(len(walkable_grid)):
            for x in range(len(walkable_grid[0])):
                if walkable_grid[y][x] and (x, y) not in visited:
                    # Found new connected area - flood fill it
                    room_tiles = self._flood_fill((x, y), walkable_grid, visited)
                    
                    # Classify as room (large open area) vs corridor (narrow passage)
                    room_type = self._classify_area(room_tiles)
                    rooms.append({
                        'type': room_type,
                        'tiles': room_tiles,
                        'center': self._find_room_center(room_tiles),
                        'connections': self._find_connections(room_tiles, walkable_grid)
                    })
        
        return rooms
    
    def _classify_area(self, tiles):
        """Determine if area is room, corridor, or junction"""
        if len(tiles) < 10:
            return 'corridor'
        elif len(tiles) > 50:
            return 'room'
        else:
            # Check aspect ratio for corridor vs room distinction
            bounds = self._get_bounding_box(tiles)
            aspect = max(bounds['width'], bounds['height']) / min(bounds['width'], bounds['height'])
            return 'corridor' if aspect > 3 else 'room'

**Approach C: LLM Strategic Prompting**
```
## EXPLORATION STRATEGY
You are playing Diablo I. Your PRIMARY GOAL is to clear each dungeon level completely:

1. **Explore systematically** - Don't leave areas unchecked
2. **Track your progress** - Use exploration data to identify unexplored areas  
3. **Clear before progressing** - Don't advance to next level until current level is 100% clear
4. **Remember the goal** - You're hunting Diablo through 16 levels of dungeons

Current Level Completion: {completion_percentage}%
Unexplored Areas: {frontier_tiles}
```

### 2. Town Knowledge & NPCs
**Issue**: AI doesn't understand town layout or utilize NPCs strategically.

**Approach A: Town State Enhancement**
```cpp
// In GAP state extraction
struct TownNPCs {
    Point healer_pos = {43, 21};      // Pepin the Healer
    Point smith_pos = {62, 16};       // Griswold the Blacksmith  
    Point witch_pos = {80, 20};       // Adria the Witch
    Point storyteller_pos = {25, 51}; // Deckard Cain
    Point boy_pos = {75, 44};        // Wirt
    Point dungeon_entrance = {25, 20};
};

// Add to JSON state when in_town=true
"town_npcs": {
    "healer": {"pos": [43, 21], "service": "healing", "distance": 12},
    "smith": {"pos": [62, 16], "service": "repair_buy_sell", "distance": 8}
}
```

**Approach B: Strategic Town Behavior**
```
## TOWN STRATEGY
When in town, you have specific objectives:

**Health Management**: 
- HP < 50%? Visit Pepin the Healer at (43,21)
- Damaged equipment? Visit Griswold at (62,16)

**Resource Management**:
- Low on potions? Buy from Pepin or Adria
- Need equipment upgrades? Check Griswold's shop
- Gold management: Sell items before dungeon runs

**Quest Management**:
- Talk to Deckard Cain for quest information
- Check Wirt for rare items (if you have gold)

**Dungeon Preparation**:
- Stock up on health potions
- Ensure equipment is repaired  
- Only enter dungeon when fully prepared
```

**Approach C: Economic Intelligence**
```python
class EconomicAI:
    def __init__(self):
        self.gold_history = []  # track spending patterns
        self.item_values = {}  # learned value of different items
        self.shopping_priorities = ['health_potions', 'repairs', 'upgrades']
        self.vendor_prices = {}  # remember NPC pricing
        
    def evaluate_purchase_decision(self, item, cost, current_gold, player_needs):
        """Smart purchasing logic based on needs and budget"""
        # Priority scoring system
        need_scores = {
            'health_potion': 100 if player_needs.hp_low else 20,
            'mana_potion': 80 if player_needs.mana_low else 10,
            'equipment_repair': 90 if player_needs.damaged_gear else 0,
            'weapon_upgrade': 70 if item.damage > player_needs.current_weapon_damage else 0,
            'armor_upgrade': 60 if item.armor > player_needs.current_armor else 0
        }
        
        # Budget constraints
        affordable = cost <= current_gold * 0.8  # keep 20% buffer
        good_value = cost <= self.item_values.get(item.type, float('inf'))
        
        priority_score = need_scores.get(item.type, 0)
        return affordable and (priority_score > 50 or good_value)
    
    def track_spending(self, purchase_type, amount, outcome_rating):
        """Learn from purchases - was it worth it?"""
        self.gold_history.append({
            'type': purchase_type,
            'cost': amount,
            'outcome': outcome_rating,  # 1-10 scale
            'timestamp': time.time()
        })
        
        # Adjust future valuations based on outcomes
        if outcome_rating < 5:
            # Bad purchase - reduce valuation
            self.item_values[purchase_type] *= 0.9
        elif outcome_rating > 7:
            # Good purchase - increase valuation
            self.item_values[purchase_type] *= 1.1

### 3. Strategic Goal Hierarchy
**Issue**: AI lacks overarching goals and quest understanding.

**Approach A: Goal-Oriented Architecture**
```python
class DiabloGoals:
    def __init__(self):
        self.primary_goal = "kill_diablo"
        self.current_objectives = []
        self.level_goals = {}
        self.quest_states = {}
    
    def get_current_objective(self, game_state):
        if game_state.player.in_town:
            return self._town_objectives(game_state)
        else:
            return self._dungeon_objectives(game_state)
    
    def _dungeon_objectives(self, state):
        level = state.player.level
        completion = self.get_level_completion(level)
        
        if completion < 0.95:
            return f"explore_and_clear_level_{level}"
        else:
            return f"find_stairs_to_level_{level + 1}"
```

**Approach B: Quest System Integration**
```cpp
// Add quest state to GAP protocol
struct QuestState {
    bool poisoned_water_active = false;
    bool butcher_alive = true;
    bool skeleton_king_alive = true;
    int current_dungeon_level = 1;
    int max_dungeon_level_reached = 1;
};

// Include in JSON state
"quest_state": {
    "current_level": 3,
    "max_level_reached": 5,
    "active_quests": ["poisoned_water", "butcher"],
    "completed_quests": ["skeleton_king"]
}
```

**Approach C: Strategic Prompt Enhancement**
```
## DIABLO I STRATEGIC CONTEXT

**Your Mission**: Descend through 16 dungeon levels to defeat Diablo in Hell.

**Current Status**: 
- Level: {current_level}/16
- Progress: {(current_level/16)*100:.1f}% to Diablo
- Goal: {current_objective}

**Level Strategy**:
- Levels 1-4: Church (Cathedral)
- Levels 5-8: Catacombs  
- Levels 9-12: Caves
- Levels 13-16: Hell

**Completion Requirements Per Level**:
1. Kill all monsters (100% clear)
2. Loot all chests/barrels
3. Find the stairs down
4. Only then proceed to next level

**Quest Integration**: Some levels have special areas to explore (like Butcher's chamber). Always fully clear before progressing.
```

### 4. Enhanced Spatial Reasoning
**Issue**: AI doesn't understand room structure or navigate complex layouts effectively.

**Approach A: Room Detection Algorithm**
```python
class SpatialIntelligence:
    def __init__(self):
        self.room_memory = {}  # room_id -> room_data
        self.connection_graph = {}  # room connectivity
        self.important_locations = {}  # stairs, fountains, quest areas
        
    def detect_rooms(self, walkable_grid, explored_area):
        """Advanced room detection with spatial analysis"""
        rooms = []
        visited = set()
        
        # Find all connected components (potential rooms)
        for y in range(len(walkable_grid)):
            for x in range(len(walkable_grid[0])):
                if walkable_grid[y][x] and (x, y) not in visited:
                    room_tiles = self._flood_fill_room((x, y), walkable_grid, visited)
                    room_analysis = self._analyze_room_structure(room_tiles, walkable_grid)
                    
                    if room_analysis['type'] == 'room':
                        rooms.append({
                            'id': len(rooms),
                            'tiles': room_tiles,
                            'center': room_analysis['center'],
                            'type': room_analysis['subtype'],  # 'treasure', 'boss', 'regular'
                            'entrances': room_analysis['entrances'],
                            'tactical_value': self._rate_tactical_value(room_analysis)
                        })
        
        return rooms
    
    def _analyze_room_structure(self, tiles, walkable_grid):
        """Detailed room analysis for tactical planning"""
        center = self._find_geometric_center(tiles)
        entrances = self._find_room_entrances(tiles, walkable_grid)
        
        # Classify room type based on structure
        area = len(tiles)
        entrance_count = len(entrances)
        
        if area > 100 and entrance_count == 1:
            subtype = 'boss_room'  # Large room with single entrance
        elif area < 20 and any(self._near_stairs(tile) for tile in tiles):
            subtype = 'stair_room'  # Small room near stairs
        elif len([tile for tile in tiles if self._has_objects_nearby(tile)]) > area * 0.3:
            subtype = 'treasure_room'  # Many chests/barrels
        else:
            subtype = 'regular'
            
        return {
            'center': center,
            'entrances': entrances,
            'type': 'room',
            'subtype': subtype,
            'area': area
        }
    
    def _rate_tactical_value(self, room_analysis):
        """Score rooms for tactical importance"""
        base_score = room_analysis['area']  # Larger rooms = higher value
        
        # Bonus for special room types
        type_bonuses = {
            'boss_room': 100,
            'treasure_room': 80,
            'stair_room': 90,
            'regular': 20
        }
        
        # Penalty for multiple entrances (harder to defend)
        entrance_penalty = len(room_analysis['entrances']) * 10
        
        return base_score + type_bonuses.get(room_analysis['subtype'], 0) - entrance_penalty

**Approach B: Landmark Navigation**
```python
class LandmarkSystem:
    def __init__(self):
        self.landmarks = {}  # landmark_id -> {pos, type, connections}
        self.navigation_graph = {}  # landmark connections for pathfinding
        self.landmark_history = {}  # when we last visited each landmark
        
    def detect_landmarks(self, game_state):
        """Automatically detect important navigation points"""
        new_landmarks = []
        
        # Stairs are always landmarks
        if 'stairs_visible' in game_state.exploration:
            stairs_pos = tuple(game_state.exploration['stairs_pos'])
            self.add_landmark(f"stairs_{game_state.level}", stairs_pos, 'stairs')
        
        # Room centers for navigation hubs
        for room in game_state.detected_rooms:
            center = tuple(room['center'])
            self.add_landmark(f"room_{room['id']}_center", center, 'room_center')
        
        # Objects of interest (fountains, shrines)
        for obj in game_state.objects:
            if obj['type'] in ['fountain', 'shrine']:
                pos = tuple(obj['pos'])
                self.add_landmark(f"{obj['type']}_{pos[0]}_{pos[1]}", pos, obj['type'])
        
        return new_landmarks
    
    def find_path_via_landmarks(self, current_pos, target_pos):
        """High-level pathfinding using landmark graph"""
        # Find nearest landmarks to start and end
        start_landmark = self._find_nearest_landmark(current_pos)
        end_landmark = self._find_nearest_landmark(target_pos)
        
        if start_landmark and end_landmark:
            # Use A* on landmark graph for high-level path
            landmark_path = self._landmark_astar(start_landmark, end_landmark)
            
            # Convert landmark path to waypoint sequence
            waypoints = [current_pos]
            for landmark_id in landmark_path:
                waypoints.append(self.landmarks[landmark_id]['pos'])
            waypoints.append(target_pos)
            
            return waypoints
        
        # Fallback to direct pathfinding
        return [current_pos, target_pos]
    
    def _landmark_astar(self, start_id, goal_id):
        """A* pathfinding on landmark graph"""
        # Simplified A* implementation for landmark navigation
        open_set = [(0, start_id)]
        came_from = {}
        g_score = {start_id: 0}
        
        while open_set:
            current_f, current = heapq.heappop(open_set)
            
            if current == goal_id:
                # Reconstruct path
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                return path[::-1]
            
            for neighbor in self.navigation_graph.get(current, []):
                tentative_g = g_score[current] + self._landmark_distance(current, neighbor)
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._landmark_distance(neighbor, goal_id)
                    heapq.heappush(open_set, (f_score, neighbor))
        
        return []  # No path found

**Approach C: Intelligent Exploration Patterns**
```
## SPATIAL REASONING ENHANCEMENT

**Room Analysis**: 
- Large open areas = likely important (boss rooms, treasure rooms)
- Narrow passages = corridors connecting rooms
- Dead ends = check carefully for secrets/loot

**Exploration Pattern**:
1. **Systematic sweep**: Clear each room completely before moving on
2. **Corridor mapping**: Use corridors to navigate between rooms
3. **Landmark tracking**: Remember key locations (stairs, fountains, quest areas)
4. **Completionist approach**: Check every corner, alcove, and side passage

**Navigation Strategy**:
- Prioritize unexplored rooms over corridors
- Always clear rooms fully before leaving
- Use central locations as navigation hubs
- Mark and return to partially explored areas
```

### 5. Natural Language Interface
**Issue**: No communication capability between AI and human player.

**Approach A: Chat Integration**
```python
class DiabloChat:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.conversation_history = []
        self.game_context = None
    
    async def respond_to_player(self, message, game_state):
        """AI can discuss strategy, explain decisions, ask for help"""
        context = f"Game State: Level {game_state.level}, HP: {game_state.hp}/{game_state.hp_max}"
        
        prompt = f"""
        You are an AI playing Diablo I alongside a human player. 
        Current situation: {context}
        Player says: "{message}"
        
        Respond as your AI character would - discuss strategy, ask questions, or explain your current actions.
        """
        
        return await self.llm.query(prompt)
```

**Approach B: Decision Explanation**
```python
# Add reasoning to all AI decisions
{
    "intent": {"type": "intent", "action": "move", "params": {"x": 45, "y": 32}},
    "reasoning": "Moving to unexplored room - only 67% of level cleared, need to find remaining monsters before advancing",
    "strategy": "systematic_exploration",
    "chat_message": "I'm heading to that unexplored room to the east - we need to clear this level completely before finding the stairs."
}
```

**Approach C: Strategic Consultation**
```python
class StrategicConsultation:
    def __init__(self):
        self.pending_questions = []
        self.decision_history = []
        self.player_preferences = {}  # learned player decision patterns
        
    def should_ask_for_guidance(self, situation):
        """Determine when AI should consult human player"""
        consultation_triggers = {
            'exploration_stuck': self._exploration_completion() > 0.9 and self._monsters_remaining() > 0,
            'resource_decision': self._low_resources() and self._multiple_options_available(),
            'tactical_uncertainty': self._facing_boss() and self._low_health(),
            'quest_confusion': self._quest_objective_unclear(),
            'equipment_choice': self._multiple_good_upgrades_available()
        }
        
        for trigger, condition in consultation_triggers.items():
            if condition and trigger not in [q['type'] for q in self.pending_questions]:
                return trigger
        
        return None
    
    def generate_consultation_prompt(self, situation_type, context):
        """Create intelligent consultation questions"""
        prompts = {
            'exploration_stuck': f"""
            I've cleared {context['completion']}% of {context['level_name']} Level {context['level_num']}, 
            but can't find the remaining {context['monsters_left']} monsters. Should I:
            A) Keep searching systematically room by room
            B) Look for secret doors or hidden passages  
            C) Proceed to find stairs (might miss loot/XP)
            D) Use a different search pattern
            
            Current strategy: {context['current_strategy']}
            """,
            
            'resource_decision': f"""
            I'm running low on resources with {context['hp_percent']}% HP and {context['gold']} gold.
            Available options:
            A) Return to town for healing and supplies ({context['town_distance']} tiles away)
            B) Use remaining {context['potions']} potions and continue exploring
            C) Play more cautiously and avoid combat until safer
            
            Risk assessment: {context['danger_level']}
            """,
            
            'tactical_uncertainty': f"""
            Facing {context['boss_name']} with {context['hp_percent']}% HP.
            Boss appears to have {context['boss_hp_percent']}% health remaining.
            
            Tactical options:
            A) Continue aggressive assault 
            B) Retreat and heal, then return
            C) Try kiting/hit-and-run tactics
            D) Use special items/abilities
            
            What's your preferred strategy for this situation?
            """
        }
        
        return prompts.get(situation_type, f"Need guidance on: {situation_type}")
    
    def learn_from_consultation(self, question_type, player_choice, outcome_success):
        """Update AI preferences based on player guidance results"""
        self.decision_history.append({
            'type': question_type,
            'player_choice': player_choice,
            'success': outcome_success,
            'timestamp': time.time()
        })
        
        # Learn player preferences for future autonomous decisions
        if question_type not in self.player_preferences:
            self.player_preferences[question_type] = {}
        
        choice_key = player_choice.split(')')[0]  # Extract A, B, C, etc.
        if choice_key not in self.player_preferences[question_type]:
            self.player_preferences[question_type][choice_key] = {'count': 0, 'success_rate': 0}
        
        prefs = self.player_preferences[question_type][choice_key]
        prefs['count'] += 1
        prefs['success_rate'] = (prefs['success_rate'] * (prefs['count'] - 1) + outcome_success) / prefs['count']
```

---

## Implementation Priority Matrix

### Phase 0: Protocol Enhancements (High Impact, Low Effort) ⭐ **IMMEDIATE**
**Target: Robust Foundation - Complete Basic Survival Loop**

#### A. New Intent Types (Lock Protocol v0.3)
```json
// Enhanced interaction capabilities
{"type":"intent","data":{"cmd":"cast","slot":1,"x":52,"y":47,"targetTick":12346}}
{"type":"intent","data":{"cmd":"pickup","id":16}}  // item by ID
{"type":"intent","data":{"cmd":"use_potion","kind":"hp"}}  // or {"slot":0}
{"type":"intent","data":{"cmd":"interact","id":301}}  // doors/chests/stairs
{"type":"intent","data":{"cmd":"path","x":80,"y":12}}  // long-range pathfinding
{"type":"intent","data":{"cmd":"explore"}}  // frontier-based exploration
```

#### B. Standard Error Handling
```json
// Consistent error responses for debugging
"rate_limited", "not_ready", "invalid_position", "unreachable", 
"late_tick", "out_of_range", "cooldown"
```

#### C. Essential State Additions
```json
"player": {
  "belt": [{"t":"hp","n":2},{"t":"mp","n":1},null,null],
  "spells": {"slot1":"Firebolt","slot2":"TownPortal"}
},
"objects": [
  {"id":301,"kind":"chest","pos":[49,44],"locked":false},
  {"id":302,"kind":"stairs_down","pos":[60,15]}
],
"exploration": {
  "seen_mask": "RLE_encoded_bitstring",  // memory efficient
  "frontiers": [[x,y], [x,y]]  // explorable boundary tiles
}
```

#### D. Survival Reflex System (Python Layer)
```python
class SurvivalReflexes:
    """Critical survival logic that overrides LLM decisions"""
    def __init__(self):
        self.last_potion_time = 0
        self.potion_cooldown = 500  # ms
        
    def check_emergency_actions(self, state):
        """Non-negotiable survival responses"""
        current_time = state['timestamp']
        player = state['player']
        
        # Emergency healing
        if player['hp'] / player['hp_max'] < 0.25:
            if current_time - self.last_potion_time >= self.potion_cooldown:
                self.last_potion_time = current_time
                return {"type":"intent","data":{"cmd":"use_potion","kind":"hp"}}
        
        # Pre-emptive healing under heavy fire
        incoming_dps = self._estimate_incoming_damage(state['monsters'])
        if incoming_dps > 0 and player['hp'] / incoming_dps < 1.2:  # < 1.2s to live
            if current_time - self.last_potion_time >= self.potion_cooldown:
                self.last_potion_time = current_time
                return {"type":"intent","data":{"cmd":"use_potion","kind":"hp"}}
        
        return None  # No emergency action needed
```

#### E. Robust Navigation System
```python
class WaypointPlanner:
    def __init__(self):
        self.blocked_edges = {}  # cache blocked paths temporarily
        self.stuck_counter = 0
        self.last_position = None
        
    def plan_route(self, current_pos, target_pos, walkable_grid):
        """A* pathfinding with waypoint chunking"""
        path = self._astar(current_pos, target_pos, walkable_grid)
        if not path:
            # Fallback: frontier A* toward unexplored areas
            path = self._frontier_astar(current_pos, walkable_grid)
        
        # Chunk into 3-5 tile waypoints to prevent getting stuck
        return self._chunk_path(path, chunk_size=4)
    
    def handle_stuck_detection(self, current_pos):
        """Detect and resolve stuck situations"""
        if current_pos == self.last_position:
            self.stuck_counter += 1
            if self.stuck_counter > 12:  # ~400ms of no movement
                # Mark current path as blocked, try alternative
                return True
        else:
            self.stuck_counter = 0
        
        self.last_position = current_pos
        return False
```

#### F. Systematic Exploration Algorithm
```python
def exploration_step(state):
    """Frontier-based exploration for complete level coverage"""
    seen_mask = decode_seen_mask(state['exploration']['seen_mask'])
    
    # Find frontier cells: unseen but adjacent to seen walkable tiles
    frontiers = []
    for y in range(seen_mask.height):
        for x in range(seen_mask.width):
            if not seen_mask[y][x] and is_adjacent_to_seen(x, y, seen_mask):
                frontiers.append((x, y))
    
    if not frontiers:
        return None  # Exploration complete
    
    # Select closest frontier by A* distance
    current_pos = state['player']['pos']
    best_frontier = min(frontiers, key=lambda f: astar_distance(current_pos, f))
    
    return {"type":"intent","data":{"cmd":"path","x":best_frontier[0],"y":best_frontier[1]}}
```

#### G. Spell Casting Implementation (C++ Side)
```cpp
// Server-side spell casting integration
// Uses same mechanics as UI click-to-cast for consistency
namespace devilution::gap {
    
enum class IntentResult {
    Success,
    RateLimited,
    NotReady, 
    InvalidPosition,
    Unreachable,
    LateTick,
    OutOfRange,
    Cooldown
};

class SpellCaster {
public:
    IntentResult HandleCastIntent(const CastIntent& intent) {
        // Get actual spell ID from hotkey slot
        SpellID spellId = GetPlayerSpellFromSlot(intent.slot);
        if (spellId == SpellID::Invalid) {
            return IntentResult::NotReady;
        }
        
        // Check cooldown (same as UI casting)
        if (!CanCastSpell(spellId)) {
            return IntentResult::Cooldown; 
        }
        
        // Range validation
        Point playerPos = Players[MyPlayerId].position.tile;
        Point targetPos = {intent.x, intent.y};
        if (!IsSpellInRange(spellId, playerPos, targetPos)) {
            return IntentResult::OutOfRange;
        }
        
        // Execute cast using existing game functions
        IssueCastAtPosition(spellId, targetPos);
        return IntentResult::Success;
    }
    
    IntentResult HandleInteractIntent(const InteractIntent& intent) {
        // Find object by ID
        Object* obj = FindObjectById(intent.id);
        if (!obj) {
            return IntentResult::InvalidPosition;
        }
        
        // Check if reachable (adjacent for doors/chests)
        Point playerPos = Players[MyPlayerId].position.tile;
        if (DistanceToObject(playerPos, obj->position) > 1) {
            return IntentResult::Unreachable;
        }
        
        // Use existing interaction system
        InteractWithObject(*obj);
        return IntentResult::Success;
    }
};

} // namespace devilution::gap
```

#### H. Configuration & Environment Setup
```ini
# gap.ini - Runtime configuration
[gap]
socket_path = /tmp/devilutionx_gap.sock
tick_divisor = 4        # Publish state every 4 ticks (~133ms at 30 FPS)
max_send_buffer = 65536 # 64KB backpressure limit
debug_overlay = false   # Draw waypoints/errors on screen
replay_log = true       # Log decisions for debugging

[limits]
commands_per_second = 10
max_path_distance = 50   # tiles
potion_cooldown_ms = 500

[llm]
model = qwen2.5:3b
timeout_ms = 2000
context_window = 4096
```

**Expected Result**: Robust, non-crashing AI that survives encounters and systematically clears levels

### Phase 1: Core Exploration (High Impact, Medium Effort)
**Target: Systematic Level Clearing**
- Implement DungeonMemory class with exploration tracking
- Add frontier tile detection to GAP state extraction  
- Enhance LLM prompt with completion percentage context
- **Expected Result**: AI clears 95%+ of each level before advancing

### Phase 2: Strategic Intelligence (High Impact, High Effort)
**Target: Goal-Oriented Behavior**
- Add quest state tracking to GAP protocol
- Implement goal hierarchy system in MCP server
- Create strategic prompting with mission context
- **Expected Result**: AI understands its overarching mission and makes strategic decisions

### Phase 3: Spatial Intelligence (Medium Impact, High Effort)  
**Target: Advanced Navigation**
- Room detection and analysis system
- Landmark-based navigation graphs
- Tactical positioning for combat
- **Expected Result**: AI navigates complex layouts efficiently and uses terrain tactically

### Phase 4: Social Intelligence (Medium Impact, Medium Effort)
**Target: Town NPC Integration**
- Add town NPC locations and services to state
- Economic decision-making for purchases
- Resource management strategies
- **Expected Result**: AI manages resources intelligently and utilizes town services strategically

### Phase 5: Communication Layer (Low Impact, Low Effort)
**Target: Human-AI Collaboration**
- Chat integration for strategy discussion
- Decision explanation system
- Strategic consultation prompts
- **Expected Result**: Enhanced debugging and collaborative gameplay experience

---

## Technical Architecture Considerations

### State Management Scaling
```python
# Current: Single JSON blob
# Future: Modular state components
class GapStateManager:
    def __init__(self):
        self.components = {
            'player': PlayerStateComponent(),
            'combat': CombatStateComponent(), 
            'exploration': ExplorationStateComponent(),
            'inventory': InventoryStateComponent(),
            'social': SocialStateComponent()  # NPCs, multiplayer
        }
    
    def get_contextual_state(self, situation):
        """Return only relevant state for current situation"""
        if situation == 'combat':
            return ['player', 'combat']
        elif situation == 'town':
            return ['player', 'inventory', 'social']
        else:
            return ['player', 'exploration']
```

### LLM Context Window Management
```python
class ContextWindowManager:
    def __init__(self, max_tokens=4096):
        self.max_tokens = max_tokens
        self.priority_weights = {
            'combat_state': 100,  # Always include if monsters present
            'player_status': 90,   # HP, mana, position
            'immediate_environment': 80,  # Visible tiles, items
            'exploration_progress': 70,   # Completion status
            'strategic_context': 60,      # Goals, quests
            'historical_context': 30      # Previous actions
        }
    
    def optimize_context(self, full_state):
        """Intelligently trim context to fit window while preserving critical info"""
        # Token counting and prioritization logic
        pass
```

### Performance Optimization Strategies
1. **Delta State Updates**: Only send changes since last tick
2. **Semantic Compression**: Convert raw game data to LLM-friendly summaries
3. **Predictive Caching**: Pre-compute likely LLM responses for common situations
4. **Parallel Processing**: Run exploration analysis while LLM processes combat decisions

---

## Integration with Existing Codebase

### Minimal Invasive Changes
The GAP system should remain optional and non-intrusive:

```cpp
// Source/diablo.cpp - Enhanced integration points
void game_loop(bool bStartup) {
    // Existing game logic...
    
#ifdef ENABLE_GAP
    static uint32_t last_gap_tick = 0;
    if (SDL_GetTicks() - last_gap_tick > GAP_UPDATE_INTERVAL) {
        gap::PublishState(sgGameInitInfo.nTickRate);
        last_gap_tick = SDL_GetTicks();
    }
#endif
}

// Source/gap/gap_extensions.cpp - New file for advanced features
namespace devilution::gap {
    class ExplorationTracker {
        // Track visited tiles across game sessions
        // Persistent exploration data
    };
    
    class QuestTracker {  
        // Monitor quest states and objectives
        // Integration with existing quest system
    };
}
```

### Backward Compatibility
- All GAP features behind compile flags
- No changes to core game mechanics
- Optional MCP server component
- Graceful degradation when LLM unavailable

---

## Testing and Validation Framework

### Phase 0 Validation Tests (Run Tonight)
**Immediate verification of core functionality:**

1. **Town Exploration Test**
```python
# Spiral "explore" command should fill Tristram square without getting stuck
def test_town_exploration():
    # Start at town center
    # Issue explore commands until no more frontiers
    # Verify: no stuck loops, covers >95% of walkable area
    assert exploration_coverage > 0.95
    assert no_stuck_loops
```

2. **Pathfinding Around Obstacles**
```python
# A* should reach visible chest around walls via waypoints
def test_obstacle_navigation():
    target = find_nearest_chest()
    path = planner.plan_route(player_pos, target, walkable_grid)
    # Verify: path exists, avoids walls, uses 3-5 tile chunks
    assert path is not None
    assert all(is_walkable(waypoint) for waypoint in path)
    assert max_waypoint_distance <= 5
```

3. **Basic Combat Survival**
```python
# 1v1 skeleton: melee at 1-2 tiles, retreat to 3+ tiles, re-engage
def test_combat_kiting():
    # Spawn single skeleton
    # Verify: approaches to distance 1-2, attacks, retreats to 3+
    combat_log = simulate_skeleton_fight()
    assert min_combat_distance <= 2
    assert retreat_distance >= 3
    assert survived_encounter
```

4. **Emergency Healing**
```python
# Script HP drop; reflex should pre-pot once, then respect cooldown
def test_emergency_healing():
    player.hp = player.hp_max * 0.2  # Drop to 20%
    action = survival_reflexes.check_emergency_actions(state)
    assert action['data']['cmd'] == 'use_potion'
    
    # Should not spam potions
    action2 = survival_reflexes.check_emergency_actions(state) 
    assert action2 is None  # Cooldown active
```

5. **Door Interaction**
```python
# Goal behind closed door → interact(door) then resume path
def test_door_handling():
    target_behind_door = (50, 30)
    door_id = find_blocking_door(player_pos, target_behind_door)
    
    path_result = navigation.plan_route(player_pos, target_behind_door)
    assert path_result.requires_door_interaction
    assert path_result.door_id == door_id
```

### AI Behavior Metrics
```python
class AIPerformanceMetrics:
    def __init__(self):
        self.metrics = {
            'exploration_efficiency': [],  # % of level cleared per minute
            'combat_success_rate': [],     # monster kills vs deaths
            'resource_management': [],     # gold efficiency, potion usage
            'strategic_decision_quality': [], # quest completion, goal achievement
            'pathfinding_efficiency': []   # distance traveled vs optimal path
        }
    
    def evaluate_session(self, session_data):
        """Generate performance report for AI behavior tuning"""
        pass
```

### Development Ergonomics (Fast Iteration)
```python
class DebugSystem:
    def __init__(self):
        self.replay_buffer = collections.deque(maxlen=1000)
        self.debug_overlay = DebugOverlay()
    
    def log_decision(self, tick, state_hash, intent, result):
        """Append to replay log for debugging combat issues"""
        self.replay_buffer.append({
            'tick': tick,
            'state_hash': state_hash,
            'intent': intent,
            'result': result,
            'timestamp': time.time()
        })
        
        # Auto-save when errors occur
        if result.get('error'):
            self.save_replay_segment(tick - 50, tick + 10)
    
    def draw_debug_overlay(self, game_state):
        """Optional: draw current subgoal and last error over player"""
        if self.debug_overlay.enabled:
            self.debug_overlay.draw_waypoint(game_state.current_subgoal)
            self.debug_overlay.draw_error(game_state.last_error)
```

### IPC & Resilience Improvements
```python
class RobustGAPServer:
    def __init__(self):
        self.send_buffer_max = 64 * 1024  # 64KB buffer
        self.connected_clients = []
        
    def publish_state(self, state_json):
        """Backpressure: if send buffer full → skip frame; never block"""
        for client in self.connected_clients[:]:  # Copy list for safe iteration
            try:
                if client.send_buffer_full():
                    # Skip this frame for this client, don't block game
                    continue
                client.send(state_json)
            except BrokenPipeError:
                # Client disconnected, remove cleanly
                self.connected_clients.remove(client)
    
    def handle_reconnection(self, new_client):
        """Accept new client cleanly after disconnect"""
        self.connected_clients.append(new_client)
        # Send current state immediately for fast catch-up
        self.publish_state(self.get_current_state())
```

### Advanced Testing Scenarios
1. **Exploration Completeness**: Can AI find 100% of Cathedral Level 1?
2. **Combat Effectiveness**: Survival rate against different monster types
3. **Resource Optimization**: Efficient gold spending and item management
4. **Strategic Thinking**: Does AI prioritize long-term goals over short-term gains?
5. **Adaptability**: Response to unexpected situations (surrounded, low health, etc.)

---

## Future Vision: Advanced AI Capabilities

### Machine Learning Integration
- **Behavior Cloning**: Learn from expert human players
- **Reinforcement Learning**: Optimize strategies through self-play  
- **Curriculum Learning**: Progressive difficulty increase
- **Multi-Agent Systems**: Coordinate multiple AI characters

### Advanced Strategic Planning  
- **Monte Carlo Tree Search**: Evaluate multiple strategy branches
- **Predictive Modeling**: Anticipate monster spawns and player needs
- **Dynamic Strategy Adaptation**: Adjust playstyle based on success metrics
- **Meta-Learning**: Improve learning efficiency across multiple playthroughs

### Emergent Behaviors
- **Personality Development**: Unique AI playstyles emerge over time
- **Social Learning**: AI learns from observing other players
- **Creative Problem Solving**: Novel solutions to complex situations
- **Storytelling**: AI narrates its adventures and decision-making process

The GAP system provides a foundation for all of these advanced capabilities while maintaining the authentic Diablo experience.
