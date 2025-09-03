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
                 personality: str = "balanced", compact: bool = True):
        self.gap_socket_path = gap_socket_path
        self.ollama_url = ollama_url
        self.model = model
        self.password = password
        self.personality = personality
        self.compact = compact
        self.gap_socket = None
        self.session = None
        
        # State management for freshness
        self.last_processed_tick = 0
        self.last_decision_time = 0
        self.min_decision_interval = 0.5  # Minimum 500ms between decisions
        self.last_player_pos = None
        self.decision_timeout = 2.0  # Max 2s per decision
        
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
- You receive game state as JSON with: player HP/mana/position, nearby monsters, items, walkable grid
- You respond with GAP intent JSON to control the character
- Available intents: move (to position), attack (monster ID or position)

## Intent Format:
Move: {"type": "intent", "action": "move", "params": {"x": 50, "y": 45}}
Attack Monster: {"type": "intent", "action": "attack", "params": {"x": monster_id, "y": -1}}
Attack Position: {"type": "intent", "action": "attack", "params": {"x": 50, "y": 45}}

## Decision Making:
- Prioritize survival: retreat when health is low
- Target closest hostile monsters first  
- Collect valuable items (gold, potions, equipment)
- Use the walkable grid to plan safe paths
- Consider monster HP and distance for tactical decisions

## Response Format:
Respond with a single valid GAP intent JSON object. No explanation, just the JSON.
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
                "capabilities": ["move", "attack", "use_item", "pickup"]
            }
            
            if self.password:
                hello_msg["password"] = self.password
                
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

    async def query_ollama(self, prompt: str) -> Optional[str]:
        """Query Ollama API with the given prompt."""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent decisions
                    "top_p": 0.9
                }
            }
            
            async with self.session.post(f"{self.ollama_url}/api/generate", 
                                       json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "").strip()
                else:
                    logger.error(f"Ollama API error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error querying Ollama: {e}")
            return None

    def compress_game_state(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Compress game state to essential information only."""
        try:
            data = game_state.get("data", {})
            
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
            
            # Extract 5x5 grid centered on player
            compressed_grid = []
            if walkable_grid and len(walkable_grid) > 5:
                mid = len(walkable_grid) // 2
                for row in walkable_grid[mid-2:mid+3]:
                    if len(row) > 5:
                        col_mid = len(row) // 2
                        compressed_grid.append(row[col_mid-2:col_mid+3])
            
            return {
                "player": compressed_player,
                "monsters": essential_monsters,
                "items": essential_items,
                "walkable": compressed_grid  # 5x5 grid only
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

    async def process_game_state(self, state_msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process game state and generate intent via LLM."""
        import time
        
        # Check if we should process this state
        if not self.should_process_state(state_msg):
            return None
            
        try:
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
            data = state_msg.get("data", {})
            player = data.get("player", {})
            self.last_player_pos = player.get("pos", [0, 0])
                
            # Parse LLM response as JSON
            try:
                # Extract JSON from response (may have extra text)
                start_idx = response.find('{')
                end_idx = response.rfind('}') + 1
                
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = response[start_idx:end_idx]
                    llm_response = json.loads(json_str)
                    
                    # Check if response has feedback channel
                    if "intent" in llm_response and "feedback" in llm_response:
                        # Extract intent for game and feedback for logging
                        intent = llm_response["intent"]
                        feedback = llm_response["feedback"]
                        action_type = intent.get("action", "unknown")
                        logger.info(f"🤖 AI: {feedback}")
                        logger.info(f"➡️  {action_type.upper()}: {intent}")
                        return intent
                    elif "type" in llm_response and llm_response.get("type") == "intent":
                        # Direct intent format (backward compatibility)
                        action_type = llm_response.get("action", "unknown")
                        logger.info(f"➡️  {action_type.upper()}: {llm_response}")
                        return llm_response
                    else:
                        # Handle nested intent format {"intent": {...}}
                        if "intent" in llm_response:
                            intent = llm_response["intent"]
                            action_type = intent.get("action", "unknown")
                            logger.info(f"➡️  {action_type.upper()} (nested): {intent}")
                            return intent
                        else:
                            logger.error(f"Invalid response format: {llm_response}")
                            return None
                else:
                    logger.error(f"No valid JSON found in LLM response: {response}")
                    return None
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.error(f"Response was: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing game state: {e}")
            return None

    async def run(self):
        """Main server loop."""
        logger.info("Starting MCP Server for GAP Protocol")
        
        # Create HTTP session for Ollama
        self.session = aiohttp.ClientSession()
        
        try:
            # Connect to GAP
            if not await self.connect_gap():
                return
            
            logger.info("MCP Server ready - processing game states...")
            
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
    print()
    
    server = GapMCPServer(
        gap_socket_path=args.socket,
        ollama_url=args.ollama_url,
        model=args.model,
        password=args.password,
        personality=args.personality,
        compact=not args.full_context
    )
    
    # Run the server
    asyncio.run(server.run())

if __name__ == "__main__":
    main()