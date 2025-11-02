#!/usr/bin/env python3
"""
DSL-based GAP agent with persistent memory

Compact, fast, memory-enabled AI companion for DevilutionX.
"""

import socket
import struct
import requests
import logging
import time
import argparse
from typing import Optional
from dsl_parser import parse_dsl_state, build_llm_summary
from memory_store import MemoryStore
from chat_handler import ChatHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SOCKET_PATH = "/tmp/devilutionx-gap.sock"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Terse system prompt - optimized for 7-8B models
SYSTEM_PROMPT = """You are a Diablo companion. Output ONE command only:

MV x y  (move to position)
AT id   (attack monster - use ONLY the ID number, nothing else)
PK id   (pick up item - use ONLY the ID number, nothing else)
CS slot (cast scroll from belt slot 0-7)
SAY text (chat)

Examples:
- Monster 82@81,46 → output: AT 82
- Item 71@35,19 → output: PK 71
- SAFE_TILE=79,65 → output: MV 79 65
- Belt has sh (heal scroll) at slot 2 → output: CS 2

RISK=high? Move to SAFE_TILE.
Monsters nearby? Attack closest.
Low HP + have healing scroll? Use CS command.
No explanations."""


class DSLAgent:
    """Main GAP agent with DSL protocol and memory"""

    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        ollama_url: str = OLLAMA_URL,
        model: str = "qwen2.5:3b",
        password: Optional[str] = None,
        think_interval: float = 1.0,
    ):
        self.socket_path = socket_path
        self.ollama_url = ollama_url
        self.model = model
        self.password = password
        self.think_interval = think_interval

        self.sock = None
        self.memory = MemoryStore()
        self.last_think_time = 0
        self.last_state = None

        # Separate chat handler (runs in thread, non-blocking)
        self.chat_handler = ChatHandler(
            send_message_callback=self._send_message_internal,
            use_llm=False  # Use templates only for instant responses
        )

        logger.info(f"DSL Agent initialized")
        logger.info(f"  Model: {model}")
        logger.info(f"  Think interval: {think_interval}s")
        logger.info(f"  Chat: Template-based (non-blocking)")

    def connect(self):
        """Connect to GAP Unix socket and send handshake"""
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect(self.socket_path)
            self.sock.settimeout(0.1)  # Non-blocking with timeout
            logger.info(f"✅ Connected to {self.socket_path}")

            # Note: In DSL mode, handshake might be handled differently
            # The game should accept DSL commands directly
            # But if password authentication is needed, we'd send it here
            if self.password:
                logger.info(f"Password provided: {self.password}")
                # In DSL mode, authentication might need to be implemented
                # For now, just log it
        except Exception as e:
            logger.error(f"❌ Failed to connect to {self.socket_path}: {e}")
            raise

    def recv_message(self) -> Optional[str]:
        """Receive length-prefixed message from socket"""
        try:
            # Read 4-byte length header
            length_bytes = self.sock.recv(4)
            if len(length_bytes) < 4:
                return None

            length = struct.unpack('<I', length_bytes)[0]

            # Read message data
            data = b""
            while len(data) < length:
                chunk = self.sock.recv(length - len(data))
                if not chunk:
                    return None
                data += chunk

            return data.decode('utf-8')

        except socket.timeout:
            return None
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            return None

    def _send_message_internal(self, msg: str):
        """Internal send (for chat handler callback)"""
        try:
            data = msg.encode('utf-8')
            length = struct.pack('<I', len(data))
            self.sock.sendall(length + data)
            logger.debug(f"📤 Sent: {msg[:50]}...")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    def send_message(self, msg: str):
        """Send length-prefixed message to socket"""
        self._send_message_internal(msg)

    def query_llm(self, prompt: str, timeout: float = 30.0) -> str:
        """Query Ollama for decision"""
        try:
            full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"

            # Ollama request with strict parameters for reliability
            request_payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "num_ctx": 512,           # Small context window
                    "temperature": 0.2,       # Low temp for consistency
                    "top_p": 0.8,             # Focused sampling
                    "repeat_penalty": 1.1,    # Avoid repetition
                    "num_predict": 16,        # Force concise output
                }
            }

            # Add grammar constraint if supported (Ollama 0.1.17+)
            # This forces valid DSL output and eliminates parsing errors
            request_payload["grammar"] = '''
root ::= ( mv | at | pk | in | say )
mv    ::= "MV " [0-9]+ " " [0-9]+
at    ::= "AT " [0-9]+
pk    ::= "PK " [0-9]+
in    ::= "IN " [0-9]+
say   ::= "SAY " [^\\n]+
'''
            logger.debug("📋 Grammar constraint enabled")

            resp = requests.post(
                self.ollama_url,
                json=request_payload,
                timeout=timeout
            )
            resp.raise_for_status()

            response_text = resp.json()["response"].strip()
            logger.debug(f"🔍 RAW LLM RESPONSE: {response_text[:200]}")

            # Extract first valid DSL line
            for line in response_text.split('\n'):
                line = line.strip()
                # Remove markdown/code block artifacts
                line = line.replace('```', '').strip()

                if not line or line.startswith('#'):
                    continue

                # Reject lines with pipe characters (LLM confusion)
                if '|' in line:
                    logger.warning(f"Rejecting invalid format with pipe: {line}")
                    continue

                # Strip label prefixes if LLM copies the examples
                # "ATTACK: AT 174" -> "AT 174"
                # "MOVE: MV 35 42" -> "MV 35 42"
                # "PICKUP: PK 13" -> "PK 13"
                for prefix in ['ATTACK:', 'MOVE:', 'PICKUP:', 'CHAT:']:
                    if line.startswith(prefix):
                        line = line[len(prefix):].strip()
                        break

                # Sanitize common LLM format mistakes
                # Fix: "MV x=35,y=42" or "MV x35,y42" -> "MV 35 42"
                if line.startswith('MV'):
                    # Remove x=/y= prefixes and commas
                    line = line.replace('x=', '').replace('y=', '').replace('x', '').replace('y', '').replace(',', ' ')
                    # Clean up extra spaces
                    parts = line.split()
                    if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                        line = f"MV {parts[1]} {parts[2]}"
                    else:
                        logger.warning(f"Invalid MV format: {line}")
                        continue

                # Fix: "AT id=35" or "AT:35" -> "AT 35"
                elif line.startswith('AT'):
                    line = line.replace('id=', '').replace(':', ' ')
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        line = f"AT {parts[1]}"
                    else:
                        logger.warning(f"Invalid AT format: {line}")
                        continue

                # Fix: "PK id=71" -> "PK 71"
                elif line.startswith('PK'):
                    line = line.replace('id=', '').replace(':', ' ')
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        line = f"PK {parts[1]}"
                    else:
                        logger.warning(f"Invalid PK format: {line}")
                        continue

                # SAY is always valid
                elif line.startswith('SAY'):
                    return line

                # IN is simple format
                elif line.startswith('IN'):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        return f"IN {parts[1]}"
                    else:
                        continue

                else:
                    continue  # Unknown command

                # If we get here, line is valid
                return line

            # Fallback if no valid command
            logger.warning(f"LLM returned no valid command: {response_text[:100]}")
            return "SAY Thinking..."

        except requests.exceptions.Timeout:
            logger.warning("LLM query timed out")
            return "SAY Timeout..."
        except Exception as e:
            logger.error(f"LLM query failed: {e}")
            return "SAY Error"

    def update_memory(self, state: dict):
        """Update memory based on current state"""
        tick = state["tick"]
        floor = state["floor"]
        me_x, me_y, hp_pct, mp_pct = state["me"]

        # Mark current position as explored
        self.memory.mark_area_explored(floor, me_x, me_y, "visited", tick)

        # Check for low health (danger area)
        if hp_pct < 30:
            self.memory.mark_area_explored(floor, me_x, me_y, "DANGER_low_hp", tick)

        # Record nearby monsters (combat context)
        for mob in state["mobs"][:3]:  # Top 3 closest
            if mob["dist"] <= 5:  # Very close
                outcome = "engaging" if hp_pct > 50 else "retreating"
                self.memory.add_encounter(
                    f"monster_{mob['id']}", mob["x"], mob["y"], outcome, tick
                )

        # Auto-create exploration goals if none exist
        active_goals = self.memory.get_active_goals()
        if not active_goals and floor > 0:  # In dungeon, no goals
            self.memory.add_goal("explore", f"floor_{floor}", tick)
            logger.info(f"Created exploration goal for floor {floor}")

        # Cleanup old data periodically
        if tick % 10000 == 0:
            self.memory.cleanup_old_data(tick, retention_ticks=50000)

    def warmup_llm(self):
        """Warm up the LLM by loading the model into memory"""
        logger.info("🔥 Warming up LLM (loading model into memory)...")
        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": "Hi",
                    "stream": False,
                    "options": {"num_predict": 1}
                },
                timeout=60.0  # Generous timeout for first load
            )
            resp.raise_for_status()
            logger.info("✅ LLM warmed up and ready")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to warm up LLM: {e}")
            return False

    def should_think(self) -> bool:
        """Decide if it's time to ask LLM for decision"""
        now = time.time()

        # Think on regular interval
        if now - self.last_think_time >= self.think_interval:
            return True

        return False

    def run(self):
        """Main agent loop"""
        self.connect()

        # Warm up LLM before starting
        if not self.warmup_llm():
            logger.warning("⚠️ LLM warmup failed, but continuing anyway...")

        # Start chat handler thread
        self.chat_handler.start()
        logger.info("💬 Chat handler thread started")

        logger.info("🤖 Agent running! Waiting for state updates...")
        logger.info(f"💭 Think interval: {self.think_interval}s")

        state_count = 0

        try:
            while True:
                # Receive DSL message from game
                dsl_line = self.recv_message()

                if not dsl_line:
                    time.sleep(0.01)  # Small sleep to avoid busy loop
                    continue

                # Check if it's a chat message - delegate to chat handler thread
                if dsl_line.startswith("CHAT "):
                    parts = dsl_line[5:].split(": ", 1)
                    if len(parts) == 2:
                        sender, message = parts
                        logger.info(f"💬 {sender}: {message}")
                        self.chat_handler.handle_chat(sender, message)
                    continue

                # Parse state
                state = parse_dsl_state(dsl_line)

                if state["tick"] == 0:
                    continue  # Invalid state

                state_count += 1

                # Log state occasionally
                if state_count % 30 == 0:  # Every ~1 second
                    me_x, me_y, hp_pct, mp_pct = state["me"]
                    logger.info(
                        f"📥 State: tick={state['tick']} floor={state['floor']} "
                        f"pos=({me_x},{me_y}) hp={hp_pct}% mobs={len(state['mobs'])} loot={len(state['loot'])}"
                    )

                # Update memory
                self.update_memory(state)
                self.last_state = state

                # Decide if we should think
                if not self.should_think():
                    continue

                self.last_think_time = time.time()

                # Build compact LLM prompt
                summary = build_llm_summary(state, self.memory)
                logger.info(f"🧠 LLM Prompt:\n{summary}")

                # Query LLM
                start_time = time.time()
                command = self.query_llm(summary)
                query_time = time.time() - start_time

                # SURVIVAL & COMBAT LOGIC
                me_x, me_y, hp_pct, mp_pct = state["me"]

                # SURVIVAL: Retreat if low HP (override everything except SAY)
                if hp_pct < 30 and not command.startswith("SAY"):
                    if state.get("player"):
                        plyr_x, plyr_y = state["player"]
                        player_dist = abs(plyr_x - me_x) + abs(plyr_y - me_y)
                        # Move toward player for protection
                        if player_dist > 2:
                            retreat_cmd = f"MV {plyr_x} {plyr_y}"
                            logger.info(f"🏃 RETREAT (HP={hp_pct}%): {command} → {retreat_cmd}")
                            command = retreat_cmd

                # COMBAT OVERRIDE: Force attack if healthy and monsters nearby
                # (Only if HP > 35% to ensure survival)
                elif hp_pct > 35 and not command.startswith("SAY") and not command.startswith("AT"):
                    if state["mobs"] and len(state["mobs"]) > 0:
                        # Check if close to player
                        if state.get("player"):
                            plyr_x, plyr_y = state["player"]
                            player_dist = abs(plyr_x - me_x) + abs(plyr_y - me_y)
                            # If within 8 tiles of player and monsters present, attack!
                            if player_dist <= 8:
                                closest_mob = state["mobs"][0]  # Already sorted by distance
                                if closest_mob["dist"] <= 15:  # Monster within bow range
                                    override_cmd = f"AT {closest_mob['id']}"
                                    logger.info(f"⚔️ Combat override (HP={hp_pct}%): {command} → {override_cmd}")
                                    command = override_cmd

                logger.info(f"📤 Command: {command} (took {query_time:.2f}s)")

                # Send command back to game
                self.send_message(command)

        except KeyboardInterrupt:
            logger.info("\n👋 Agent stopped by user")
        except Exception as e:
            logger.error(f"💥 Agent crashed: {e}", exc_info=True)
        finally:
            self.chat_handler.stop()
            if self.sock:
                self.sock.close()
            self.memory.close()
            logger.info("🔒 Agent shutdown complete")

    def get_stats(self):
        """Get agent statistics"""
        mem_stats = self.memory.get_stats()
        return {
            "memory": mem_stats,
            "model": self.model,
            "think_interval": self.think_interval,
        }


def main():
    parser = argparse.ArgumentParser(description="DSL GAP Agent for DevilutionX")
    parser.add_argument("--socket", "-s", default=SOCKET_PATH, help="GAP socket path")
    parser.add_argument("--ollama-url", default=OLLAMA_URL, help="Ollama API URL")
    parser.add_argument("--model", "-m", default="qwen2.5:3b", help="Ollama model")
    parser.add_argument("--password", "-p", help="Game password")
    parser.add_argument("--think-interval", type=float, default=1.0, help="Seconds between decisions")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    agent = DSLAgent(
        socket_path=args.socket,
        ollama_url=args.ollama_url,
        model=args.model,
        password=args.password,
        think_interval=args.think_interval,
    )

    logger.info("=" * 60)
    logger.info("DSL GAP Agent")
    logger.info("=" * 60)
    logger.info(f"Socket: {args.socket}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Think interval: {args.think_interval}s")
    logger.info("=" * 60)

    agent.run()


if __name__ == "__main__":
    main()
