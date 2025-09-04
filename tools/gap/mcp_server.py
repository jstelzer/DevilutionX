#!/usr/bin/env python3
"""
MCP Server for DevilutionX GAP Protocol
Bridges GAP socket directly to Ollama API with structured JSON prompts
"""

import asyncio
import json
import logging
import socket
import struct
import time
from typing import Optional, Dict, Any
import aiohttp
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GapMCPServer:
    def __init__(self, gap_socket_path: str, ollama_url: str = "http://localhost:11434", 
                 model: str = "llama3.2", password: Optional[str] = None, 
                 personality: str = "balanced", compact: bool = True,
                 companion_slot: Optional[int] = None):
        self.gap_socket_path = gap_socket_path
        self.ollama_url = ollama_url
        self.model = model
        self.password = password
        self.personality = personality
        self.compact = compact
        self.companion_slot = companion_slot
        self.gap_socket = None
        self.session = None
        
        # State management for freshness
        self.last_processed_tick = 0
        self.last_decision_time = 0
        self.min_decision_interval = 0.5  # Minimum 500ms between decisions
        self.last_player_pos = None
        self.decision_timeout = 5.0  # Max 5s per decision (after warmup)
        self.warmup_timeout = 30.0  # Max 30s for initial model loading
        self.warmup_complete = False
        
        # Loop detection and attack cooldowns
        self.last_intent = None
        self.same_intent_count = 0
        self.max_same_intent = 3  # Max 3 identical attacks before changing strategy
        self.monster_attack_history = {}  # monster_id -> [timestamps]
        self.attack_cooldown = 1.0  # 1 second between attacks on same monster
        
        # Invalid intent tracking - clear context when too many invalid attempts
        self.invalid_intent_count = 0
        self.max_invalid_intents = 5  # Reset context after 5 invalid intents
        
        # Map exploration memory
        self.explored_positions = set()  # (x, y) positions visited
        self.cleared_areas = set()  # (x, y) positions fully cleared
        self.current_level = 1
        self.level_start_time = None
        
        # Pathfinding and obstacle avoidance
        self.stuck_counter = 0
        self.last_position = None
        self.stuck_threshold = 3  # If position hasn't changed for 3 decisions, we're stuck
        self.target_position = None  # Current pathfinding target
        
        # Load prompts (compact version for small context models)
        prompt_file = "compact_diablo_agent.txt" if compact else "diablo_agent.txt"
        self.base_prompt = self.load_prompt(prompt_file)
        self.personality_overlay = self.load_personality_overlay(personality)
        
    def load_prompt(self, filename: str) -> str:
        """Load prompt from file with fallback to default."""
        try:
            with open(f"prompts/{filename}", 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(f"Prompt file {filename} not found, using default")
            return self.get_default_prompt()
    
    def load_personality_overlay(self, personality: str) -> str:
        """Load personality overlay prompt."""
        if personality == "balanced" or personality == "default":
            return ""  # No overlay for balanced personality
        
        try:
            with open(f"prompts/{personality}.txt", 'r') as f:
                overlay = f.read().strip()
                logger.info(f"Loaded personality: {personality}")
                return overlay
        except FileNotFoundError:
            logger.warning(f"Personality file {personality}.txt not found, using balanced")
            return ""
    
    def get_default_prompt(self) -> str:
        """Default GAP protocol prompt."""
        return """You are an AI agent playing Diablo I via the GAP (Game Agent Protocol).

## GAP Protocol Overview:
- You receive game state as JSON with: player HP/mana/position, nearby monsters, items, walkable grid, chat messages
- You respond with GAP intent JSON to control the character
- Available intents: move (to position), attack (monster ID or position), chat (respond to player)

## CRITICAL: Response Format
You MUST respond with valid JSON in this EXACT format (no extra text):

For movement:
{"intent": {"type": "intent", "action": "move", "params": {"x": 75, "y": 68}}}

For attack:
{"intent": {"type": "intent", "action": "attack", "params": {"x": monster_id, "y": -1}}}

For chat:
{"intent": {"type": "intent", "action": "chat", "params": {"kind": "Your message here"}}}

NEVER include any text before or after the JSON. The JSON must be complete and valid.

## Intent Format:
Move: {"type": "intent", "action": "move", "params": {"x": 50, "y": 45}}
Attack Monster: {"type": "intent", "action": "attack", "params": {"x": monster_id, "y": -1}}
Attack Position: {"type": "intent", "action": "attack", "params": {"x": 50, "y": 45}}
Chat Response: {"type": "intent", "action": "chat", "params": {"kind": "Your message here"}}

## Decision Making:
- Prioritize survival: retreat when health is low
- Target closest hostile monsters first  
- Collect valuable items (gold, potions, equipment)
- Use the walkable grid to plan safe paths
- Consider monster HP and distance for tactical decisions
- If player sends chat messages, respond conversationally as their AI companion
- Chat responses should be helpful and match your current situation

## Response Format:
Respond with a single valid GAP intent JSON object. No explanation, just the JSON.
If player is chatting with you, prioritize chat response over combat (unless in immediate danger).
"""

    async def connect_gap(self) -> bool:
        """Connect to GAP socket and perform handshake."""
        try:
            logger.info(f"Connecting to GAP socket: {self.gap_socket_path}")
            self.gap_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.gap_socket.connect(self.gap_socket_path)
            
            # Perform handshake
            hello_msg = {
                "type": "hello",
                "version": "0.2.0", 
                "capabilities": ["move", "attack", "use_item", "pickup", "chat"]
            }
            
            if self.password:
                hello_msg["password"] = self.password
                
            if self.companion_slot is not None:
                hello_msg["control_player"] = self.companion_slot
                
            await self.send_gap_message(hello_msg)
            
            # Wait for hello response
            response = await self.read_gap_message()
            if response and response.get("type") == "hello":
                logger.info("GAP handshake successful")
                logger.info(f"Game version: {response.get('version')}")
                logger.info(f"Tick rate: {response.get('tick_rate')}")
                return True
            else:
                logger.error(f"Unexpected handshake response: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to GAP: {e}")
            return False

    async def send_gap_message(self, msg: Dict[str, Any]) -> bool:
        """Send message to GAP socket."""
        try:
            # Debug: Log movement details
            if msg.get('action') == 'move':
                params = msg.get('params', {})
                target_x = params.get('x', 0)
                target_y = params.get('y', 0)
                logger.info(f"🚶 SENDING MOVE to GAP: target=({target_x},{target_y})")
                
            data = json.dumps(msg).encode('utf-8')
            length = struct.pack('<I', len(data))
            self.gap_socket.sendall(length + data)
            return True
        except Exception as e:
            logger.error(f"Error sending GAP message: {e}")
            return False

    async def read_gap_message(self) -> Optional[Dict[str, Any]]:
        """Read message from GAP socket."""
        try:
            # Read 4-byte length prefix
            length_bytes = self.gap_socket.recv(4)
            if len(length_bytes) != 4:
                return None
                
            length = struct.unpack('<I', length_bytes)[0]
            
            # Read JSON payload
            data = b''
            while len(data) < length:
                chunk = self.gap_socket.recv(min(4096, length - len(data)))
                if not chunk:
                    return None
                data += chunk
                
            decoded_data = data.decode('utf-8', errors='replace')
            if not decoded_data.strip():
                logger.warning("Received empty message from GAP socket")
                return None
            return json.loads(decoded_data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Raw data length: {len(data)}, content: {data[:100]}...")
            return None
        except Exception as e:
            logger.error(f"Error reading GAP message: {e}")
            return None

    async def warmup_model(self):
        """Warm up the model with a simple query to avoid cold start delays."""
        if self.warmup_complete:
            return
        
        logger.info(f"🔥 Warming up model {self.model}... (this may take 30+ seconds for first load)")
        warmup_prompt = "Hello! Just respond with 'Ready' in JSON format: {\"response\": \"Ready\"}"
        
        try:
            # Use longer timeout for warmup
            timeout = aiohttp.ClientTimeout(total=self.warmup_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as warmup_session:
                payload = {
                    "model": self.model,
                    "prompt": warmup_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9
                    }
                }
                
                start_time = time.time()
                async with warmup_session.post(f"{self.ollama_url}/api/generate", json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        warmup_time = time.time() - start_time
                        logger.info(f"🎯 Model warmed up successfully! Took {warmup_time:.1f}s")
                        self.warmup_complete = True
                        return True
                    else:
                        logger.error(f"Warmup failed with status: {response.status}")
                        return False
        except asyncio.TimeoutError:
            logger.error(f"Model warmup timed out after {self.warmup_timeout}s")
            return False
        except Exception as e:
            logger.error(f"Error during model warmup: {e}")
            return False

    async def query_ollama(self, prompt: str) -> Optional[str]:
        """Query Ollama API with the given prompt."""
        try:
            # Use appropriate timeout based on warmup status
            current_timeout = self.warmup_timeout if not self.warmup_complete else self.decision_timeout
            timeout = aiohttp.ClientTimeout(total=current_timeout)
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent decisions
                    "top_p": 0.9
                }
            }
            
            # Create session with timeout for this query
            async with aiohttp.ClientSession(timeout=timeout) as query_session:
                async with query_session.post(f"{self.ollama_url}/api/generate", 
                                           json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if not self.warmup_complete:
                            logger.info("🎯 Model is now warmed up for future requests")
                            self.warmup_complete = True
                        return result.get("response", "").strip()
                    else:
                        logger.error(f"Ollama API error: {response.status}")
                        return None
        except asyncio.TimeoutError:
            timeout_desc = "warmup" if not self.warmup_complete else "query"
            logger.warning(f"LLM {timeout_desc} timed out after {current_timeout}s - skipping")
            return None
        except Exception as e:
            logger.error(f"Error querying Ollama: {e}")
            return None

    def compress_game_state(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Compress game state to essential information only."""
        try:
            data = game_state.get("data", {})
            
            # Debug: Log the raw game state structure to understand chat data location
            nearby_data = data.get('nearby', {})
            if 'chat' in nearby_data:
                logger.info(f"💬 DEBUG: Found chat in data.nearby: {nearby_data['chat']}")
            elif 'chat' in data:
                logger.info(f"💬 DEBUG: Found chat in data: {data['chat']}")
            elif 'chat' in game_state:
                logger.info(f"💬 DEBUG: Found chat at top level: {game_state['chat']}")
            else:
                # Log full structure to find where chat might be  
                full_json = json.dumps(game_state, indent=2)
                logger.info(f"💬 DEBUG: No chat found. JSON length: {len(full_json)} chars")
                logger.info(f"💬 DEBUG: Full game state structure: {full_json[:500]}...")
                logger.info(f"💬 DEBUG: JSON ends with: ...{full_json[-100:]}")
            
            # Essential player info
            player = data.get("player", {})
            compressed_player = {
                "hp": player.get("hp", 0),
                "hp_max": player.get("hp_max", 1),
                "pos": player.get("pos", [0, 0])
            }
            
            # Debug: Check raw monster data
            nearby = data.get("nearby", {})
            monsters = nearby.get("monsters", [])
            # Filter monsters - only include relevant, actionable threats
            alive_monsters = []
            for monster in monsters:
                is_alive = monster.get("is_alive")
                is_minion = monster.get("is_minion")
                distance = monster.get("distance", 999)
                hp_percent = monster.get("hp_percent", 100)
                
                # Skip dead monsters
                if is_alive is False:
                    continue
                    
                # Skip minions (player summons)
                if is_minion is True:
                    continue
                    
                # Skip monsters that are too far to be relevant (>15 tiles)
                if distance > 15:
                    continue
                    
                # Skip monsters with 0 HP (dead but not marked as dead yet)
                if hp_percent <= 0:
                    continue
                
                alive_monsters.append(monster)
            
            # Sort by distance
            sorted_monsters = sorted(alive_monsters, key=lambda m: m.get("distance", 999))
            
            essential_monsters = []
            for monster in sorted_monsters[:5]:  # Top 5 threats
                dist = monster.get("distance", 999)
                essential_monsters.append({
                    "id": monster.get("id"),
                    "name": monster.get("name", "Unknown")[:8],
                    "pos": monster.get("pos"),
                    "dist": dist,
                    "hp%": monster.get("hp_percent", 100),
                    "threat": "HIGH" if dist <= 3 else "MED" if dist <= 6 else "LOW"
                })
            
            # Essential items (top 3 closest)
            items = nearby.get("items", [])
            essential_items = []
            for item in items[:3]:  # Limit to 3 items
                essential_items.append({
                    "id": item.get("id"),
                    "name": item.get("name", "Item")[:10],  # Truncate names
                    "type": item.get("type", "unknown"),
                    "pos": item.get("pos")
                })
            
            # Compressed walkable grid (5x5 around player instead of full radius)
            vision = nearby.get("vision", {})
            walkable_grid = vision.get("walkable_grid", [])
            player_pos = vision.get("player_pos", [0, 0])
            exploration_data = vision.get("exploration", {})
            
            # Update exploration memory
            current_level = exploration_data.get("current_level", 1)
            if current_level != self.current_level:
                # New level - reset exploration data
                logger.info(f"Entered new level: {current_level}")
                self.explored_positions.clear()
                self.cleared_areas.clear()
                self.current_level = current_level
                self.level_start_time = time.time()
            
            # Mark current position as explored
            pos_tuple = (player_pos[0], player_pos[1])
            if pos_tuple not in self.explored_positions:
                self.explored_positions.add(pos_tuple)
                
            # Check if current area is clear of monsters (can mark as cleared)
            if not alive_monsters and pos_tuple not in self.cleared_areas:
                self.cleared_areas.add(pos_tuple)
                
            # Extract stairs and object information from exploration data
            stairs_visible = exploration_data.get("stairs_visible", False)
            stairs_info = {}
            if stairs_visible:
                stairs_info = {
                    "pos": exploration_data.get("stairs_pos", []),
                    "type": exploration_data.get("stairs_type", ""),
                    "distance": self._calculate_distance(player_pos, exploration_data.get("stairs_pos", []))
                }
            
            # Extract objects (chests, barrels, etc.)
            objects_data = exploration_data.get("objects", [])
            
            # Extract 5x5 grid centered on player
            compressed_grid = []
            if walkable_grid and len(walkable_grid) > 5:
                mid = len(walkable_grid) // 2
                for row in walkable_grid[mid-2:mid+3]:
                    if len(row) > 5:
                        col_mid = len(row) // 2
                        compressed_grid.append(row[col_mid-2:col_mid+3])
            
            # Add exploration progress info
            exploration_progress = {
                "explored_tiles": len(self.explored_positions),
                "cleared_tiles": len(self.cleared_areas), 
                "current_level": self.current_level,
                "level_completion": f"{len(self.cleared_areas)}/{len(self.explored_positions)}" if self.explored_positions else "0/0"
            }
            
            # Add stairs information if visible
            if stairs_visible and stairs_info:
                exploration_progress["stairs"] = stairs_info
            
            # Add nearby objects for exploration
            if objects_data:
                exploration_progress["objects"] = objects_data[:5]  # Limit to 5 closest objects
            
            # Extract chat messages for AI awareness
            # Chat is nested inside 'nearby' in the GAP protocol
            chat_data = nearby.get('chat', {})
            recent_messages = chat_data.get('recent_messages', [])
            
            # Debug logging for chat
            if chat_data:
                logger.info(f"💬 CHAT DATA FOUND: {chat_data}")
            else:
                logger.debug("💬 No chat data in game state")
            
            if recent_messages:
                logger.info(f"💬 RECENT MESSAGES: {len(recent_messages)} messages found")
                for i, msg in enumerate(recent_messages):
                    logger.info(f"💬   [{i}] From: '{msg.get('from', '')}' Text: '{msg.get('text', '')}'")
            else:
                logger.debug("💬 No recent messages in chat data")
            
            chat_summary = []
            for msg in recent_messages[-3:]:  # Last 3 messages only
                msg_from = msg.get('from', '')
                msg_text = msg.get('text', '')
                if msg_from == 'player' and msg_text:  # Only include player messages
                    chat_summary.append(f"Player: {msg_text}")
                    logger.info(f"💬 ADDED TO LLM CONTEXT: Player: {msg_text}")
            
            # Add navigation awareness context
            navigation_context = {
                "stuck_counter": self.stuck_counter,
                "is_stuck": self.stuck_counter >= self.stuck_threshold,
                "position_changed": self.last_position != (player_pos[0], player_pos[1]) if self.last_position else True,
            }
            
            # Analyze walkable directions for LLM awareness
            walkable_directions = self._analyze_walkable_directions(player_pos, compressed_grid)
            navigation_context["walkable_directions"] = walkable_directions
            
            # Check if direct path to common targets is blocked and add distance info
            if exploration_progress.get("stairs"):
                stairs_pos = exploration_progress["stairs"]["pos"]
                direct_blocked = not self._is_direct_path_clear(player_pos, stairs_pos, compressed_grid)
                stairs_distance = abs(stairs_pos[0] - player_pos[0]) + abs(stairs_pos[1] - player_pos[1])
                navigation_context["stairs_path_blocked"] = direct_blocked
                navigation_context["stairs_distance"] = stairs_distance
            
            # Special handling for town -> dungeon entrance (ONLY when in town)
            if data.get("player", {}).get("in_town", False):
                dungeon_entrance = [25, 20]  # Known dungeon entrance coordinates
                entrance_distance = abs(dungeon_entrance[0] - player_pos[0]) + abs(dungeon_entrance[1] - player_pos[1])
                entrance_blocked = not self._is_direct_path_clear(player_pos, dungeon_entrance, compressed_grid)
                
                # Calculate next waypoint for long distances
                if entrance_distance > 10:
                    next_waypoint = self._calculate_next_waypoint(player_pos, dungeon_entrance)
                    navigation_context["suggested_waypoint"] = next_waypoint
                    navigation_context["waypoint_distance"] = abs(next_waypoint[0] - player_pos[0]) + abs(next_waypoint[1] - player_pos[1])
                else:
                    navigation_context["suggested_waypoint"] = dungeon_entrance
                    navigation_context["waypoint_distance"] = entrance_distance
                    
                navigation_context["dungeon_entrance_distance"] = entrance_distance
                navigation_context["dungeon_entrance_blocked"] = entrance_blocked
                navigation_context["is_far_from_entrance"] = entrance_distance > 10
                navigation_context["location"] = "town"
            else:
                # In dungeon - clear town navigation, focus on exploration/combat
                navigation_context["location"] = "dungeon"
                navigation_context["priority"] = "combat_and_exploration"
                # Clear town-specific navigation hints
                navigation_context["suggested_waypoint"] = None
                navigation_context["is_far_from_entrance"] = False
            
            return {
                "player": compressed_player,
                "monsters": essential_monsters,
                "items": essential_items,
                "walkable": compressed_grid,  # 5x5 grid only
                "exploration": exploration_progress,
                "navigation": navigation_context,
                "chat": chat_summary  # Recent player messages for AI awareness
            }
            
        except Exception as e:
            logger.error(f"Error compressing game state: {e}")
            return {"error": "compression_failed"}
    
    def build_prompt(self, game_state: Dict[str, Any]) -> str:
        """Build complete prompt with protocol docs + personality + game state."""
        if self.compact:
            # Use compressed state for small context models
            state_data = self.compress_game_state(game_state)
            state_json = json.dumps(state_data, separators=(',', ':'))
            prompt_parts = [
                self.base_prompt,
                self.personality_overlay,
                "## STATE:",
                state_json,
                "\nIntent:"
            ]
        else:
            # Use full state for larger context models
            prompt_parts = [
                self.base_prompt,
                self.personality_overlay,
                "## Current Game State:",
                json.dumps(game_state, indent=2),
                "",
                "Generate a GAP intent JSON:"
            ]
        
        return "\n".join(part for part in prompt_parts if part.strip())

    def should_process_state(self, state_msg: Dict[str, Any]) -> bool:
        """Determine if we should process this state or skip it."""
        import time
        
        current_time = time.time()
        current_tick = state_msg.get("tick", 0)
        
        # Skip if too soon since last decision
        if current_time - self.last_decision_time < self.min_decision_interval:
            return False
            
        # Skip if this tick is older than what we already processed
        if current_tick <= self.last_processed_tick:
            logger.debug(f"Skipping stale tick {current_tick} (last processed: {self.last_processed_tick})")
            return False
            
        # Check if player position changed (indicates fresh state)
        data = state_msg.get("data", {})
        player = data.get("player", {})
        current_pos = player.get("pos", [0, 0])
        
        if self.last_player_pos and current_pos == self.last_player_pos:
            # Same position, only process if there are monsters nearby
            nearby = data.get("nearby", {})
            monsters = nearby.get("monsters", [])
            if not monsters:
                logger.debug("Same position, no monsters - skipping redundant state")
                return False
        
        return True
        
    def validate_intent(self, intent: Dict[str, Any], game_state: Dict[str, Any]) -> bool:
        """Validate intent against current game state to prevent impossible actions."""
        if not intent or not isinstance(intent, dict):
            logger.warning("Invalid intent format: not a dict")
            self.invalid_intent_count += 1
            return False
            
        action = intent.get("action")
        params = intent.get("params", {})
        
        if action == "attack":
            # Validate monster ID attacks
            monster_id = params.get("x")
            attack_y = params.get("y", 0)
            
            if attack_y == -1 and monster_id is not None:  # Monster ID attack
                # Check if monster ID exists in current game state
                compressed_state = self.compress_game_state(game_state) if self.compact else game_state
                monsters = compressed_state.get("monsters", [])
                valid_monster_ids = [m.get("id") for m in monsters if m.get("id") is not None]
                
                if monster_id not in valid_monster_ids:
                    logger.warning(f"🚫 INVALID INTENT: Attack on non-existent monster ID {monster_id}. Valid IDs: {valid_monster_ids}")
                    self.invalid_intent_count += 1
                    
                    # Check if we should force a context reset due to too many invalid intents
                    if self.invalid_intent_count >= self.max_invalid_intents:
                        logger.warning(f"🔄 TOO MANY INVALID INTENTS ({self.invalid_intent_count}) - context may be stale")
                        self.invalid_intent_count = 0  # Reset counter
                        # Clear any sticky state that might cause repeated invalid intents
                        self.last_intent = None
                        self.same_intent_count = 0
                        self.monster_attack_history.clear()
                    
                    return False
                    
        elif action == "pickup":
            # Could add item validation here in the future
            pass
            
        elif action == "interact":
            # Could add object validation here in the future  
            pass
            
        elif action == "move":
            # Basic bounds checking could be added
            x, y = params.get("x", 0), params.get("y", 0)
            if x < 0 or y < 0 or x > 112 or y > 112:  # Diablo map bounds
                logger.warning(f"🚫 INVALID INTENT: Move to out-of-bounds position ({x}, {y})")
                self.invalid_intent_count += 1
                return False
                
        # Valid intent - reset invalid counter
        self.invalid_intent_count = 0
        return True
        
    def detect_stuck_loop(self, intent: Dict[str, Any]) -> bool:
        """Detect if we're stuck in a loop with same intent."""
        import time
        
        # Check for identical intents
        if self.last_intent == intent:
            self.same_intent_count += 1
            if self.same_intent_count >= self.max_same_intent:
                logger.warning(f"Detected stuck loop - same intent {self.same_intent_count} times: {intent}")
                return True
        else:
            self.same_intent_count = 0
            self.last_intent = intent.copy()
            
        # Check attack cooldowns for specific monsters
        if intent.get("action") == "attack":
            monster_id = intent.get("params", {}).get("x")
            if monster_id and monster_id != -1:  # -1 means position attack
                current_time = time.time()
                
                # Clean old attack history
                if monster_id in self.monster_attack_history:
                    self.monster_attack_history[monster_id] = [
                        t for t in self.monster_attack_history[monster_id] 
                        if current_time - t < 5.0  # Keep last 5 seconds
                    ]
                    
                    # Check if attacking same monster too frequently
                    recent_attacks = self.monster_attack_history[monster_id]
                    if len(recent_attacks) >= 3:
                        last_attack_time = recent_attacks[-1]
                        if current_time - last_attack_time < self.attack_cooldown:
                            logger.warning(f"Attack cooldown active for monster {monster_id}")
                            return True
                
                # Record this attack
                if monster_id not in self.monster_attack_history:
                    self.monster_attack_history[monster_id] = []
                self.monster_attack_history[monster_id].append(current_time)
        
        return False

    async def process_game_state(self, state_msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process game state and generate intent via LLM."""
        import time
        
        # Check if we should process this state
        if not self.should_process_state(state_msg):
            return None
            
        try:
            # Debug: Log player position from raw state
            player_data = state_msg.get('data', {}).get('player', {})
            player_pos = player_data.get('pos', [0, 0])
            in_town = player_data.get('in_town', False)
            logger.info(f"🗺️  PROCESSING: Player at ({player_pos[0]},{player_pos[1]}) in_town={in_town}")
            
            # Detect if player is stuck
            current_pos_tuple = (player_pos[0], player_pos[1])
            if self.last_position == current_pos_tuple:
                self.stuck_counter += 1
                logger.info(f"🚧 STUCK DETECTION: Counter={self.stuck_counter}/{self.stuck_threshold}")
            else:
                self.stuck_counter = 0
                self.last_position = current_pos_tuple
            current_tick = state_msg.get("tick", 0)
            self.last_processed_tick = current_tick
            # Build prompt
            prompt = self.build_prompt(state_msg)
            
            # Query LLM
            compressed_state = self.compress_game_state(state_msg) if self.compact else state_msg
            monster_count = len(compressed_state.get("monsters", []))
            player_hp_pct = 0
            if self.compact:
                player = compressed_state.get("player", {})
                if player:
                    player_hp_pct = (player.get("hp", 0) * 100) // max(player.get("hp_max", 1), 1)
            
            logger.info(f"Situation: {monster_count} monsters nearby, player HP: {player_hp_pct}%")
            if monster_count > 0:
                closest = compressed_state.get("monsters", [{}])[0]
                logger.info(f"  Closest threat: {closest.get('name', 'Unknown')} at distance {closest.get('dist', '?')} (threat: {closest.get('threat', 'UNKNOWN')})")
            
            # Log chat messages going to LLM
            chat_messages = compressed_state.get("chat", [])
            if chat_messages:
                logger.info(f"💬 SENDING TO LLM: {len(chat_messages)} chat messages: {chat_messages}")
            else:
                logger.debug("💬 No chat messages to send to LLM")
            
            # Log the compressed state being sent to LLM for debugging
            logger.debug(f"Compressed state for LLM: {json.dumps(compressed_state, indent=2)[:500]}...")
            logger.debug("Querying LLM...")
            
            # Add timeout to LLM query to prevent getting stuck
            try:
                response = await asyncio.wait_for(
                    self.query_ollama(prompt), 
                    timeout=self.decision_timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"LLM query timed out after {self.decision_timeout}s - skipping")
                return None
            
            if not response:
                logger.error("No response from LLM")
                return None
                
            # Update timing for next decision
            self.last_decision_time = time.time()
            
            # Check if we need pathfinding assistance due to being stuck
            # BUT NEVER override combat actions - combat always has priority
            if self.stuck_counter >= self.stuck_threshold and response:
                try:
                    llm_intent = json.loads(response)
                    
                    # CRITICAL: Never override combat actions
                    if llm_intent.get('action') == 'attack':
                        logger.info(f"⚔️  COMBAT PRIORITY: Keeping attack action despite being stuck")
                        # Don't override attack actions
                    elif llm_intent.get('action') == 'move':
                        # Only override movement if we're not in immediate danger
                        compressed_state = self.compress_game_state(state_msg)
                        monsters = compressed_state.get('monsters', [])
                        
                        # Check for immediate threats (distance <= 2)
                        immediate_threats = [m for m in monsters if m.get('distance', 999) <= 2]
                        if immediate_threats:
                            logger.info(f"⚔️  COMBAT EMERGENCY: {len(immediate_threats)} threats at melee range - NO PATHFINDING")
                            # Force attack on closest threat instead of movement
                            closest_threat = min(immediate_threats, key=lambda m: m.get('distance', 999))
                            response = json.dumps({
                                "type": "intent",
                                "action": "attack",
                                "params": {"x": closest_threat['id'], "y": -1}
                            })
                            logger.info(f"⚔️  EMERGENCY ATTACK: Targeting {closest_threat['name']} (ID:{closest_threat['id']})")
                        else:
                            # Safe to do pathfinding assistance
                            target_pos = [llm_intent['params']['x'], llm_intent['params']['y']]
                            walkable_grid = compressed_state.get('walkable', [])
                            
                            better_pos = self._find_walkable_path(player_pos, target_pos, walkable_grid)
                            if better_pos:
                                logger.info(f"🧭 PATHFINDING OVERRIDE: LLM wanted {target_pos}, suggesting {better_pos}")
                                response = json.dumps({
                                    "type": "intent",
                                    "action": "move", 
                                    "params": {"x": better_pos[0], "y": better_pos[1]}
                                })
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to parse LLM response for pathfinding: {e}")
            
            data = state_msg.get("data", {})
            player = data.get("player", {})
            self.last_player_pos = player.get("pos", [0, 0])
                
            # Parse LLM response as JSON
            try:
                # Extract JSON from response (may have extra text)
                start_idx = response.find('{')
                if start_idx >= 0:
                    # Count braces to find proper end instead of using rfind
                    brace_count = 0
                    end_idx = start_idx
                    for i, char in enumerate(response[start_idx:], start_idx):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    
                    json_str = response[start_idx:end_idx]
                    # Try to fix common JSON truncation issues
                    if not json_str.endswith('}'):
                        json_str += '}'
                    llm_response = json.loads(json_str)
                else:
                    # Fallback: try to parse the whole response
                    logger.warning(f"Could not find JSON bounds, trying full response: {response[:100]}...")
                    llm_response = json.loads(response)
                
                # Check for pure nested format first: {"intent": {"type": "intent", ...}}
                if ("intent" in llm_response and 
                    isinstance(llm_response["intent"], dict) and 
                    llm_response["intent"].get("type") == "intent"):
                    intent = llm_response["intent"]
                    
                    # Validate the pure nested intent
                    if not self.validate_intent(intent, state_msg):
                        logger.warning("🚫 DISCARDING INVALID PURE NESTED INTENT - checking for chat priority")
                        
                        compressed_state = self.compress_game_state(state_msg)
                        chat_messages = compressed_state.get("chat", [])
                        monsters = compressed_state.get("monsters", [])
                        
                        if chat_messages and not monsters:
                            logger.info("💬 FORCING CHAT RESPONSE - re-prompting LLM for chat only")
                            chat_intent = {
                                "type": "intent",
                                "action": "chat", 
                                "params": {"kind": "Sorry, I'm having trouble processing that. How can I help you?"}
                            }
                            logger.info(f"💬 FORCED CHAT RESPONSE: {chat_intent}")
                            return chat_intent
                    
                    action_type = intent.get("action", "unknown")
                    logger.info(f"➡️  {action_type.upper()} (pure nested): {intent}")
                    logger.info(f"🔍 RAW LLM RESPONSE WAS: {response}")
                    return intent
                
                # Check if response has feedback channel
                elif "intent" in llm_response and "feedback" in llm_response:
                    # Extract intent for game and feedback for logging
                    intent = llm_response["intent"]
                    feedback = llm_response["feedback"]
                    action_type = intent.get("action", "unknown")
                    
                    # Special logging for chat intents
                    if action_type == "chat":
                        chat_message = intent.get("params", {}).get("kind", "")
                        logger.info(f"💬 LLM WANTS TO CHAT: '{chat_message}'")
                        
                        # Validate intent before executing
                        if not self.validate_intent(intent, state_msg):
                            logger.warning("🚫 DISCARDING INVALID INTENT - checking for chat priority")
                            
                            # If there are chat messages and no monsters, try to force a chat response
                            compressed_state = self.compress_game_state(state_msg)
                            chat_messages = compressed_state.get("chat", [])
                            monsters = compressed_state.get("monsters", [])
                            
                            if chat_messages and not monsters:
                                logger.info("💬 FORCING CHAT RESPONSE - re-prompting LLM for chat only")
                                # Re-prompt the LLM specifically for chat response
                                chat_prompt = f"{self.base_prompt}\n\n**CHAT MODE - RESPOND TO PLAYER**\nPlayer said: '{chat_messages[0].replace('Player: ', '')}'\nNo monsters nearby. Respond as a friendly AI companion in the game. Keep it brief (under 50 characters).\n\nRespond with: {{\"type\":\"intent\",\"action\":\"chat\",\"params\":{{\"kind\":\"Your response here\"}}}}"
                                
                                try:
                                    chat_response = await self.query_ollama(chat_prompt)
                                    if chat_response:
                                        # Parse the chat response
                                        start_idx = chat_response.find('{')
                                        end_idx = chat_response.rfind('}') + 1
                                        if start_idx >= 0 and end_idx > start_idx:
                                            json_str = chat_response[start_idx:end_idx]
                                            chat_intent = json.loads(json_str)
                                            logger.info(f"💬 LLM CHAT RESPONSE: {chat_intent}")
                                            return chat_intent
                                except Exception as e:
                                    logger.warning(f"Failed to get LLM chat response: {e}")
                                
                                # Fallback to hardcoded response if LLM fails
                                logger.info("💬 USING FALLBACK CHAT RESPONSE")
                                chat_intent = {
                                    "type": "intent",
                                    "action": "chat",
                                    "params": {"kind": "I'm here! No monsters around, just exploring."}
                                }
                                logger.info(f"💬 FALLBACK CHAT RESPONSE: {chat_intent}")
                                return chat_intent
                            
                            # Otherwise fallback to movement
                            logger.warning("🚫 DISCARDING INVALID INTENT - forcing fallback movement")
                            # Try a different position to break out of invalid state
                            player = compressed_state.get("player", {})
                            pos = player.get("pos", [50, 50])
                            fallback_intent = {
                                "type": "intent",
                                "action": "move", 
                                "params": {"x": pos[0] + 1, "y": pos[1] + 1}
                            }
                            logger.info(f"➡️  MOVE (invalid-intent-fallback): {fallback_intent}")
                            return fallback_intent
                            
                        # Check for stuck loops before executing
                        if self.detect_stuck_loop(intent):
                            logger.warning("🔄 Breaking stuck loop - trying different strategy")
                            # Reset loop counter and try a movement instead
                            self.same_intent_count = 0
                            fallback_intent = {
                                "type": "intent",
                                "action": "move", 
                                "params": {"x": intent["params"]["x"] + 2, "y": intent["params"].get("y", 0) + 1}
                            }
                            logger.info(f"🤖 AI: {feedback} → OVERRIDE: Moving to break attack loop")
                            logger.info(f"➡️  MOVE (fallback): {fallback_intent}")
                            return fallback_intent
                        
                        logger.info(f"🤖 AI: {feedback}")
                        logger.info(f"➡️  {action_type.upper()}: {intent}")
                        return intent
                    elif "type" in llm_response and llm_response.get("type") == "intent":
                        # Direct intent format (backward compatibility)
                        
                        # Validate intent first
                        if not self.validate_intent(llm_response, state_msg):
                            logger.warning("🚫 DISCARDING INVALID DIRECT INTENT - checking for chat priority")
                            
                            # If there are chat messages and no monsters, try to force a chat response
                            compressed_state = self.compress_game_state(state_msg)
                            chat_messages = compressed_state.get("chat", [])
                            monsters = compressed_state.get("monsters", [])
                            
                            if chat_messages and not monsters:
                                logger.info("💬 FORCING CHAT RESPONSE - re-prompting LLM for chat only")
                                # Re-prompt the LLM specifically for chat response
                                chat_prompt = f"{self.base_prompt}\n\n**CHAT MODE - RESPOND TO PLAYER**\nPlayer said: '{chat_messages[0].replace('Player: ', '')}'\nNo monsters nearby. Respond as a friendly AI companion in the game. Keep it brief (under 50 characters).\n\nRespond with: {{\"type\":\"intent\",\"action\":\"chat\",\"params\":{{\"kind\":\"Your response here\"}}}}"
                                
                                try:
                                    chat_response = await self.query_ollama(chat_prompt)
                                    if chat_response:
                                        # Parse the chat response
                                        start_idx = chat_response.find('{')
                                        end_idx = chat_response.rfind('}') + 1
                                        if start_idx >= 0 and end_idx > start_idx:
                                            json_str = chat_response[start_idx:end_idx]
                                            chat_intent = json.loads(json_str)
                                            logger.info(f"💬 LLM CHAT RESPONSE: {chat_intent}")
                                            return chat_intent
                                except Exception as e:
                                    logger.warning(f"Failed to get LLM chat response: {e}")
                                
                                # Fallback to hardcoded response if LLM fails
                                logger.info("💬 USING FALLBACK CHAT RESPONSE")
                                chat_intent = {
                                    "type": "intent",
                                    "action": "chat",
                                    "params": {"kind": "I'm here! No monsters around, just exploring."}
                                }
                                logger.info(f"💬 FALLBACK CHAT RESPONSE: {chat_intent}")
                                return chat_intent
                                
                            # Otherwise fallback to movement
                            logger.warning("🚫 DISCARDING INVALID DIRECT INTENT - forcing fallback movement")
                            # Try a different position to break out of invalid state
                            player = compressed_state.get("player", {})
                            pos = player.get("pos", [50, 50])
                            fallback_intent = {
                                "type": "intent",
                                "action": "move", 
                                "params": {"x": pos[0] + 1, "y": pos[1] + 1}
                            }
                            logger.info(f"➡️  MOVE (invalid-direct-intent-fallback): {fallback_intent}")
                            return fallback_intent
                        
                        if self.detect_stuck_loop(llm_response):
                            logger.warning("🔄 Breaking stuck loop - trying different strategy")
                            self.same_intent_count = 0
                            # Try moving to a different position
                            player = compressed_state.get("player", {})
                            pos = player.get("pos", [50, 50])
                            fallback_intent = {
                                "type": "intent",
                                "action": "move", 
                                "params": {"x": pos[0] + 3, "y": pos[1] + 2}
                            }
                            logger.info(f"➡️  MOVE (loop-break): {fallback_intent}")
                            return fallback_intent
                        
                        action_type = llm_response.get("action", "unknown")
                        
                        # Special logging for chat intents
                        if action_type == "chat":
                            chat_message = llm_response.get("params", {}).get("kind", "")
                            logger.info(f"💬 LLM WANTS TO CHAT: '{chat_message}'")
                        
                        logger.info(f"➡️  {action_type.upper()}: {llm_response}")
                        return llm_response
                    else:
                        # Handle nested intent format {"intent": {...}}
                        if "intent" in llm_response:
                            intent = llm_response["intent"]
                            
                            # Validate nested intent
                            if not self.validate_intent(intent, state_msg):
                                logger.warning("🚫 DISCARDING INVALID NESTED INTENT - checking for chat priority")
                                
                                # If there are chat messages and no monsters, try to force a chat response
                                compressed_state = self.compress_game_state(state_msg)
                                chat_messages = compressed_state.get("chat", [])
                                monsters = compressed_state.get("monsters", [])
                                
                                if chat_messages and not monsters:
                                    logger.info("💬 FORCING CHAT RESPONSE - re-prompting LLM for chat only")
                                    # Re-prompt the LLM specifically for chat response
                                    chat_prompt = f"{self.base_prompt}\n\n**CHAT MODE - RESPOND TO PLAYER**\nPlayer said: '{chat_messages[0].replace('Player: ', '')}'\nNo monsters nearby. Respond as a friendly AI companion in the game. Keep it brief (under 50 characters).\n\nRespond with: {{\"type\":\"intent\",\"action\":\"chat\",\"params\":{{\"kind\":\"Your response here\"}}}}"
                                    
                                    try:
                                        chat_response = await self.query_ollama(chat_prompt)
                                        if chat_response:
                                            # Parse the chat response
                                            start_idx = chat_response.find('{')
                                            end_idx = chat_response.rfind('}') + 1
                                            if start_idx >= 0 and end_idx > start_idx:
                                                json_str = chat_response[start_idx:end_idx]
                                                chat_intent = json.loads(json_str)
                                                logger.info(f"💬 LLM CHAT RESPONSE: {chat_intent}")
                                                return chat_intent
                                    except Exception as e:
                                        logger.warning(f"Failed to get LLM chat response: {e}")
                                    
                                    # Fallback to hardcoded response if LLM fails
                                    logger.info("💬 USING FALLBACK CHAT RESPONSE")
                                    chat_intent = {
                                        "type": "intent",
                                        "action": "chat",
                                        "params": {"kind": "I'm here! No monsters around, just exploring."}
                                    }
                                    logger.info(f"💬 FALLBACK CHAT RESPONSE: {chat_intent}")
                                    return chat_intent
                                
                                # Otherwise fallback to movement
                                logger.warning("🚫 DISCARDING INVALID NESTED INTENT - forcing fallback movement")
                                # Try a different position to break out of invalid state
                                player = compressed_state.get("player", {})
                                pos = player.get("pos", [50, 50])
                                fallback_intent = {
                                    "type": "intent",
                                    "action": "move", 
                                    "params": {"x": pos[0] + 1, "y": pos[1] + 1}
                                }
                                logger.info(f"➡️  MOVE (invalid-nested-intent-fallback): {fallback_intent}")
                                return fallback_intent
                            
                            action_type = intent.get("action", "unknown")
                            logger.info(f"➡️  {action_type.upper()} (nested): {intent}")
                            return intent
                        else:
                            logger.error(f"Invalid response format: {llm_response}")
                            return None
                
                logger.error(f"No valid JSON found in LLM response: {response}")
                return None
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.error(f"Response was: {response}")
                
                # If we have chat messages and JSON parsing failed, force a chat response
                compressed_state = self.compress_game_state(state_msg)
                chat_messages = compressed_state.get("chat", [])
                monsters = compressed_state.get("monsters", [])
                
                if chat_messages and not monsters:
                    logger.info("💬 JSON PARSE FAILED BUT CHAT DETECTED - forcing fallback chat response")
                    chat_intent = {
                        "type": "intent",
                        "action": "chat",
                        "params": {"kind": "Sorry, I'm having trouble processing that. How can I help you?"}
                    }
                    logger.info(f"💬 FALLBACK CHAT RESPONSE: {chat_intent}")
                    return chat_intent
                
                return None
                
        except Exception as e:
            logger.error(f"Error processing game state: {e}")
            return None
            
    def _calculate_distance(self, pos1, pos2):
        """Calculate Euclidean distance between two positions"""
        if not pos1 or not pos2 or len(pos1) < 2 or len(pos2) < 2:
            return 999  # Invalid position
        return int(((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2) ** 0.5)
        
    def _find_walkable_path(self, current_pos, target_pos, walkable_grid):
        """Find a walkable intermediate position toward target"""
        if not walkable_grid or not current_pos or not target_pos:
            return None
            
        # Calculate total distance and direction
        dx = target_pos[0] - current_pos[0]
        dy = target_pos[1] - current_pos[1]
        total_distance = abs(dx) + abs(dy)  # Manhattan distance
        
        # For long distances, take smaller steps (max 3-5 tiles per move)
        max_step = 3 if total_distance > 10 else 1
        
        # Normalize movement to reasonable step size
        step_x = max(-max_step, min(max_step, dx))
        step_y = max(-max_step, min(max_step, dy))
        
        # Try direct path first (smaller step toward target)
        next_pos = [current_pos[0] + step_x, current_pos[1] + step_y]
        if self._is_position_walkable(next_pos, current_pos, walkable_grid):
            logger.info(f"🧭 INCREMENTAL PATH: Moving {step_x},{step_y} toward target (distance={total_distance})")
            return next_pos
            
        # If blocked, try alternative paths with smaller steps
        alternatives = [
            [current_pos[0] + step_x, current_pos[1]],  # Move X only
            [current_pos[0], current_pos[1] + step_y],  # Move Y only
            [current_pos[0] + (1 if step_x > 0 else -1), current_pos[1]],  # Single step X
            [current_pos[0], current_pos[1] + (1 if step_y > 0 else -1)],  # Single step Y
            [current_pos[0] - (1 if step_x > 0 else -1), current_pos[1]],  # Opposite X
            [current_pos[0], current_pos[1] - (1 if step_y > 0 else -1)],  # Opposite Y
        ]
        
        for alt_pos in alternatives:
            if self._is_position_walkable(alt_pos, current_pos, walkable_grid):
                logger.info(f"🧭 PATHFINDING: Direct path blocked, trying alternative {alt_pos}")
                return alt_pos
                
        return None
        
    def _is_position_walkable(self, target_pos, current_pos, walkable_grid):
        """Check if a position is walkable using the walkable grid"""
        if not walkable_grid or len(walkable_grid) < 5 or len(walkable_grid[0]) < 5:
            return True  # Default to walkable if no grid data
            
        # Grid is 5x5 centered on current position
        grid_center = 2
        offset_x = target_pos[0] - current_pos[0]
        offset_y = target_pos[1] - current_pos[1]
        
        grid_x = grid_center + offset_x
        grid_y = grid_center + offset_y
        
        # Check bounds
        if grid_x < 0 or grid_x >= 5 or grid_y < 0 or grid_y >= 5:
            return True  # Outside grid, assume walkable
            
        return walkable_grid[grid_y][grid_x] == True
        
    def _analyze_walkable_directions(self, current_pos, walkable_grid):
        """Analyze which directions are walkable for LLM awareness"""
        if not walkable_grid or len(walkable_grid) < 5:
            return ["north", "south", "east", "west"]  # Default all walkable
            
        directions = []
        # Check 4 cardinal directions from center (2,2)
        if walkable_grid[1][2]:  # North
            directions.append("north")
        if walkable_grid[3][2]:  # South  
            directions.append("south")
        if walkable_grid[2][3]:  # East
            directions.append("east")
        if walkable_grid[2][1]:  # West
            directions.append("west")
            
        return directions
        
    def _is_direct_path_clear(self, start_pos, target_pos, walkable_grid):
        """Check if direct path to target is clear (simplified check)"""
        if not walkable_grid or not start_pos or not target_pos:
            return True
            
        # Simple check: see if we can move 1 step toward target
        dx = target_pos[0] - start_pos[0]
        dy = target_pos[1] - start_pos[1]
        
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        
        next_pos = [start_pos[0] + step_x, start_pos[1] + step_y]
        return self._is_position_walkable(next_pos, start_pos, walkable_grid)
        
    def _calculate_next_waypoint(self, current_pos, final_target):
        """Calculate the next intermediate waypoint toward final target"""
        dx = final_target[0] - current_pos[0]
        dy = final_target[1] - current_pos[1]
        distance = abs(dx) + abs(dy)
        
        # Take steps of ~5-8 tiles for good progress
        step_size = min(8, max(3, distance // 4))
        
        # Calculate direction unit vector
        if abs(dx) + abs(dy) == 0:
            return current_pos  # Already at target
            
        # Normalize and scale
        step_x = int(step_size * dx / distance) if distance > 0 else 0
        step_y = int(step_size * dy / distance) if distance > 0 else 0
        
        waypoint = [current_pos[0] + step_x, current_pos[1] + step_y]
        
        # Ensure we don't overshoot
        if abs(waypoint[0] - final_target[0]) > abs(dx):
            waypoint[0] = final_target[0]
        if abs(waypoint[1] - final_target[1]) > abs(dy):
            waypoint[1] = final_target[1]
            
        return waypoint

    async def process_chat_message(self, chat_msg: Dict[str, Any]) -> None:
        """Process chat message and respond via LLM if from player."""
        try:
            text = chat_msg.get('text', '')
            from_user = chat_msg.get('from', '')
            
            logger.info(f"💬 CHAT: From {from_user}: {text}")
            
            # Only respond to player messages (not AI or system messages)
            if from_user == "player":
                # Build simple chat prompt without full game state (lighter weight)
                prompt = f"{self.base_prompt}\n\nPlayer said: \"{text}\"\n\nRespond with a chat intent to reply as their AI companion:"
                
                # Query LLM for response
                llm_response_text = await self.query_ollama(prompt)
                if not llm_response_text:
                    logger.error("No response from LLM for chat message")
                    return
                
                # Parse LLM response (using same logic as process_game_state)
                try:
                    # Look for JSON in response
                    start_idx = llm_response_text.find('{')
                    if start_idx >= 0:
                        # Count braces to find proper end instead of using rfind
                        brace_count = 0
                        end_idx = start_idx
                        for i, char in enumerate(llm_response_text[start_idx:], start_idx):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    end_idx = i + 1
                                    break
                        
                        json_str = llm_response_text[start_idx:end_idx]
                        # Try to fix common JSON truncation issues
                        if not json_str.endswith('}'):
                            json_str += '}'
                        llm_response = json.loads(json_str)
                    else:
                        # Fallback: try to parse the whole response
                        llm_response = json.loads(llm_response_text)
                    
                    # Check for pure nested format first: {"intent": {"type": "intent", ...}}
                    if ("intent" in llm_response and 
                        isinstance(llm_response["intent"], dict) and 
                        llm_response["intent"].get("type") == "intent"):
                        intent = llm_response["intent"]
                    else:
                        # Check for direct intent format
                        if llm_response.get("type") == "intent":
                            intent = llm_response
                        else:
                            logger.error(f"Invalid LLM chat response format: {llm_response}")
                            return
                            
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM chat response as JSON: {e}")
                    return
                except Exception as e:
                    logger.error(f"Error parsing LLM chat response: {e}")
                    return
                
                # Ensure it's a chat intent
                if intent.get('action') == 'chat':
                    # Send chat response back to game
                    success = await self.send_gap_message(intent)
                    if success:
                        logger.info(f"💬 AI Reply: {intent.get('params', {}).get('kind', 'N/A')}")
                    else:
                        logger.error("Failed to send chat response")
                else:
                    logger.warning(f"LLM generated non-chat intent for chat message: {intent.get('action')}")
            else:
                # AI or system message - just log, don't respond
                logger.debug(f"Ignoring non-player chat message from {from_user}")
                
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")

    async def run(self):
        """Main server loop."""
        logger.info("Starting MCP Server for GAP Protocol")
        
        # Create HTTP session for Ollama
        self.session = aiohttp.ClientSession()
        
        try:
            # Connect to GAP
            if not await self.connect_gap():
                return
            
            # Warm up the model to avoid cold start delays
            logger.info("MCP Server ready - warming up LLM...")
            await self.warmup_model()
            
            logger.info("🚀 Ready for game! Processing game states...")
            
            # Main message loop
            while True:
                msg = await self.read_gap_message()
                if not msg:
                    logger.error("Connection to game lost - attempting reconnection...")
                    # Try to reconnect once
                    if await self.connect_gap():
                        logger.info("Reconnected to GAP successfully")
                        continue
                    else:
                        logger.error("Failed to reconnect - shutting down")
                        break
                    
                msg_type = msg.get("type")
                
                if msg_type == "state":
                    # Process game state with LLM (includes staleness filtering)
                    intent = await self.process_game_state(msg)
                    
                    if intent:
                        # Send intent back to game
                        success = await self.send_gap_message(intent)
                        if not success:
                            logger.error("Failed to send intent - connection issue")
                    else:
                        # Most skips are due to staleness filtering - don't spam logs
                        pass
                        
                elif msg_type == "chat":
                    # Process chat message for LLM conversation
                    await self.process_chat_message(msg)
                    
                elif msg_type == "ack":
                    logger.debug("Intent acknowledged by game")
                    
                elif msg_type == "error":
                    logger.warning(f"Game error: {msg.get('reason')} - {msg.get('detail')}")
                    
                else:
                    logger.debug(f"Unknown message type: {msg_type}")
                    
        except KeyboardInterrupt:
            logger.info("Shutting down MCP Server...")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            if self.session:
                await self.session.close()
            if self.gap_socket:
                self.gap_socket.close()

def main():
    parser = argparse.ArgumentParser(description="MCP Server for DevilutionX GAP Protocol")
    parser.add_argument("--socket", "-s", default="/tmp/devilutionx-gap.sock",
                       help="GAP socket path")
    parser.add_argument("--ollama-url", default="http://localhost:11434",
                       help="Ollama API URL")
    parser.add_argument("--model", "-m", default="llama3.2",
                       help="Ollama model to use")
    parser.add_argument("--personality", default="balanced", 
                       choices=["balanced", "cautious", "aggressive", "greedy"],
                       help="AI personality (default: balanced)")
    parser.add_argument("--full-context", action="store_true", 
                       help="Use full prompts (requires large context model)")
    parser.add_argument("--password", "-p", help="Password for multiplayer games")
    parser.add_argument("--companion-slot", type=int, choices=[0, 1, 2, 3],
                       help="Player slot to control (0-3) for companion mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("=" * 60)
    print("DevilutionX GAP MCP Server")
    print("=" * 60)
    print(f"GAP Socket: {args.socket}")
    print(f"Ollama URL: {args.ollama_url}")
    print(f"Model: {args.model}")
    print(f"Personality: {args.personality}")
    print(f"Context Mode: {'Full' if args.full_context else 'Compact (default)'}")
    print(f"Password: {'***' if args.password else 'None'}")
    print(f"Companion Slot: {args.companion_slot if args.companion_slot is not None else 'Default (0)'}")
    print()
    
    server = GapMCPServer(
        gap_socket_path=args.socket,
        ollama_url=args.ollama_url,
        model=args.model,
        password=args.password,
        personality=args.personality,
        compact=not args.full_context,
        companion_slot=args.companion_slot
    )
    
    # Run the server
    asyncio.run(server.run())

if __name__ == "__main__":
    main()