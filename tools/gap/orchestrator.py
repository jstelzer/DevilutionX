#!/usr/bin/env python3
"""
Agent Council Orchestrator for DevilutionX GAP

Coordinates specialist agents to make optimal game decisions.
"""

import socket
import struct
import logging
import time
import argparse
from typing import Optional, List, Tuple
from agents.base import AgentResponse
from agents.combat import CombatAgent
from agents.healing import HealingAgent
from agents.movement import MovementAgent
from agents.loot import LootAgent
from agents.stats import StatsAgent
from agents.town import TownAgent
from agents.shopping import ShoppingAgent
from agents.inventory import InventoryAgent
from agents.griswold import GriswoldAgent
from agents.cain import CainAgent
from agents.adria import AdriaAgent
from agents.chat import ChatAgent
from dsl_parser import parse_dsl_state
from memory_store import MemoryStore, prepare_companion_state_for_db
from chat_handler import ChatHandler
from character_profile import CharacterProfile

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SOCKET_PATH = "/tmp/devilutionx-gap.sock"
OLLAMA_URL = "http://localhost:11434/api/generate"


class AgentOrchestrator:
    """Orchestrates specialist agents to make optimal decisions"""

    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        ollama_url: str = OLLAMA_URL,
        model: str = "qwen2.5:3b",
        chat_model: str = "llama3.1:8b",
        password: Optional[str] = None,
        think_interval: float = 1.0,
    ):
        self.socket_path = socket_path
        self.ollama_url = ollama_url
        self.dungeon_model = model  # Fast model for combat
        self.town_model = chat_model  # Better model for town interactions
        self.password = password
        self.think_interval = think_interval

        self.sock = None
        self.memory = MemoryStore()
        self.last_think_time = 0
        self.last_state = None
        self.current_context = None  # Track town vs dungeon for model switching
        self.profile = None  # Character profile (initialized on handshake)

        # Failure tracking to prevent infinite USE loops
        self.last_command = None
        self.last_hp = 100
        self.failed_use_count = 0

        # Hysteresis tracking to prevent ping-ponging
        self.last_decision_agent = None
        self.last_decision_time = 0

        # Track recently dropped items (for mutual support)
        self.recently_dropped_position = None
        self.recently_dropped_tick = 0

        # Initialize specialist agents
        # Start with dungeon model (most common context)
        self.combat = CombatAgent(model=model, ollama_url=ollama_url)
        self.healing = HealingAgent(model=model, ollama_url=ollama_url)
        self.loot = LootAgent(model=model, ollama_url=ollama_url)
        self.stats = StatsAgent(model=model, ollama_url=ollama_url)
        self.town = TownAgent(model=model, ollama_url=ollama_url)
        self.shopping = ShoppingAgent(model=model, ollama_url=ollama_url)
        self.inventory = InventoryAgent(model=model, ollama_url=ollama_url)
        self.griswold = GriswoldAgent(model=model, ollama_url=ollama_url)
        self.cain = CainAgent(model=model, ollama_url=ollama_url)
        self.adria = AdriaAgent(model=model, ollama_url=ollama_url)
        self.movement = MovementAgent(model=model, ollama_url=ollama_url)
        self.chat = ChatAgent(memory=self.memory, model=chat_model, ollama_url=ollama_url)

        # List of all agents for easy model switching
        self.agents = [
            self.combat, self.healing, self.loot,
            self.stats, self.town, self.shopping,
            self.inventory, self.griswold, self.cain, self.adria, self.movement,
            self.chat
        ]

        # Chat handler (runs in thread, non-blocking)
        self.chat_handler = ChatHandler(
            send_message_callback=self._send_message_internal,
            use_llm=True,  # Enable LLM for natural conversations
            model=chat_model,
            ollama_url=ollama_url
        )

        logger.info("🎯 Agent Orchestrator initialized")
        logger.info(f"  Agents: Combat, Healing, Loot, Stats, Town, Shopping, Inventory, Griswold, Cain, Adria, Movement, Chat")
        logger.info(f"  Dungeon model: {self.dungeon_model} (fast combat)")
        logger.info(f"  Town model: {self.town_model} (sophisticated interactions)")
        logger.info(f"  Think interval: {think_interval}s")
        logger.info(f"  Strategy: Context-based model switching (automatic)")

    def connect(self):
        """Connect to GAP Unix socket"""
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect(self.socket_path)
            self.sock.settimeout(0.1)
            logger.info(f"✅ Connected to {self.socket_path}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to {self.socket_path}: {e}")
            raise

    def recv_message(self) -> Optional[str]:
        """Receive length-prefixed message from socket"""
        try:
            length_bytes = self.sock.recv(4)
            if len(length_bytes) < 4:
                return None

            length = struct.unpack('<I', length_bytes)[0]

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

    def should_think(self) -> bool:
        """Decide if it's time to ask agents for decision"""
        now = time.time()
        if now - self.last_think_time >= self.think_interval:
            return True
        return False

    def _update_context_models(self, state: dict):
        """
        Update agent models based on game context (town vs dungeon).
        Only switches models when context changes to avoid overhead.
        """
        in_town = state.get("in_town", False)
        new_context = "town" if in_town else "dungeon"

        # Only switch if context changed
        if new_context != self.current_context:
            target_model = self.town_model if in_town else self.dungeon_model

            logger.info(f"🔄 Context change: {self.current_context} → {new_context}, switching to {target_model}")

            # Update all agents to use context-appropriate model
            for agent in self.agents:
                agent.set_model(target_model)

            self.current_context = new_context

    def _compute_danger(self, state: dict) -> float:
        """
        Compute deterministic danger level from game state.

        Returns:
            0.0-1.0 scalar (0.0 = safe, 1.0 = critical danger)
        """
        me_x, me_y, hp_pct, mp_pct = state.get("me", [0, 0, 100, 100])
        mobs = state.get("mobs", [])
        belt = state.get("belt", [])

        # Count potions
        hp_potions = sum(1 for slot in belt if slot in ["hp", "rj"])

        # Check for unique/boss monsters nearby
        unique_near = any(mob.get("unique", False) for mob in mobs)

        # Check for overwhelming numbers (6+ mobs)
        overwhelmed = len(mobs) >= 6

        # Danger components (weighted)
        hp_term = 1.0 - (hp_pct / 100.0)  # Low HP -> high danger
        mob_term = min(1.0, len(mobs) / 6.0)  # 6+ mobs ~ 1.0
        unique_term = 0.25 if unique_near else 0.0
        overwhelm_term = 0.25 if overwhelmed else 0.0
        no_pots_term = 0.2 if hp_potions == 0 else 0.0
        low_mana_term = 0.1 if mp_pct < 20 else 0.0

        # Weighted sum
        danger = (
            0.35 * hp_term +
            0.35 * mob_term +
            unique_term +
            overwhelm_term +
            no_pots_term +
            low_mana_term
        )

        return max(0.0, min(1.0, danger))

    def decide(self, state: dict) -> str:
        """
        Main decision loop. Collects agent recommendations and picks winner.

        Priority hierarchy (multiplier × weight):
        1. CHAT (11) - Immediate response to player questions
        2. HEALING (10/8) - HP < 25% critical, else normal
        3. STATS (9) - Character progression when points available
        4. CAIN (8) - Identify items before selling/using
        5. INVENTORY (7) - Emergency belt refills, proactive management
        6. ADRIA (7) - Witch shop for casters (mana potions, staves, books)
        7. SHOPPING (6-7) - Buy HP potions, gear upgrades
        8. GRISWOLD (6) - Sell junk items, free inventory space
        9. TOWN (5) - Navigate to NPCs, general town activities
        10. COMBAT (8/6) - Attack monsters when HP healthy
        11. LOOT (4-9) - Pick up items (priority varies by urgency)
        12. MOVEMENT (3) - Exploration and following player

        Returns:
            DSL command string
        """
        # Update models based on context (town vs dungeon)
        self._update_context_models(state)

        me_x, me_y, hp_pct, mp_pct = state["me"]

        # Compute deterministic danger level (0.0 = safe, 1.0 = critical)
        danger = self._compute_danger(state)

        # Log danger occasionally for tuning
        if state.get("tick", 0) % 60 == 0:  # Every 2 seconds
            logger.info(f"⚠️  Danger level: {danger:.2f}")

        # Collect agent recommendations
        recommendations: List[Tuple[str, AgentResponse, float]] = []

        # CHAT - highest priority when player asks a question (immediate response)
        chat_rec = self.chat.evaluate(state)
        if chat_rec and chat_rec.weight > 0.0:
            # Priority 11 for chat (player messages deserve immediate attention)
            score = chat_rec.weight * 11
            recommendations.append(("Chat", chat_rec, score))

        # HEALING - highest priority if urgent
        healing_rec = self.healing.evaluate(state)
        if healing_rec and healing_rec.weight > 0.0:
            # Priority 10 for healing, boosted if HP critical
            priority = 10 if hp_pct < 25 else 8
            score = healing_rec.weight * priority
            recommendations.append(("Healing", healing_rec, score))

        # STATS - high priority when available (character progression)
        stats_rec = self.stats.evaluate(state)
        if stats_rec and stats_rec.weight > 0.0:
            # Priority 9 for stats (character progression is critical, takes <1 second)
            score = stats_rec.weight * 9
            recommendations.append(("Stats", stats_rec, score))

        # TOWN - handle town activities
        town_rec = self.town.evaluate(state)
        if state.get("in_town") and (not town_rec or town_rec.weight == 0.0):
            logger.info(f"🏘️ Town agent: {town_rec.reasoning if town_rec else 'None'} (weight={town_rec.weight if town_rec else 'N/A'})")
        if town_rec and town_rec.weight > 0.0:
            # Priority 5 for town (shopping, repair)
            score = town_rec.weight * 5
            recommendations.append(("Town", town_rec, score))

        # CAIN - identify unidentified items (in town only)
        cain_rec = self.cain.evaluate(state)
        if state.get("in_town") and (not cain_rec or cain_rec.weight == 0.0):
            logger.info(f"🔍 Cain agent: {cain_rec.reasoning if cain_rec else 'None'} (weight={cain_rec.weight if cain_rec else 'N/A'})")
        if cain_rec and cain_rec.weight > 0.0:
            # Priority 8 for identification (need to know what items are before selling/using)
            score = cain_rec.weight * 8
            recommendations.append(("Cain", cain_rec, score))

        # GRISWOLD - sell junk items (in town only)
        griswold_rec = self.griswold.evaluate(state)
        if state.get("in_town") and (not griswold_rec or griswold_rec.weight == 0.0):
            logger.info(f"💰 Griswold agent: {griswold_rec.reasoning if griswold_rec else 'None'} (weight={griswold_rec.weight if griswold_rec else 'N/A'})")
        if griswold_rec and griswold_rec.weight > 0.0:
            # Priority 6 for selling (clear inventory, get gold)
            score = griswold_rec.weight * 6
            recommendations.append(("Griswold", griswold_rec, score))

        # INVENTORY - refill belt from inventory
        inventory_rec = self.inventory.evaluate(state)
        if state.get("in_town") and (not inventory_rec or inventory_rec.weight == 0.0):
            logger.info(f"📦 Inventory agent: {inventory_rec.reasoning if inventory_rec else 'None'} (weight={inventory_rec.weight if inventory_rec else 'N/A'})")
        if inventory_rec and inventory_rec.weight > 0.0:
            # Priority 7 for inventory (emergency belt refills can be critical)
            score = inventory_rec.weight * 7
            recommendations.append(("Inventory", inventory_rec, score))

        # ADRIA - witch shop for casters (mana potions, staves, books)
        adria_rec = self.adria.evaluate(state)
        if state.get("in_town") and (not adria_rec or adria_rec.weight == 0.0):
            logger.info(f"🔮 Adria agent: {adria_rec.reasoning if adria_rec else 'None'} (weight={adria_rec.weight if adria_rec else 'N/A'})")
        if adria_rec and adria_rec.weight > 0.0:
            # Priority 7 for Adria (casters need mana potions!)
            score = adria_rec.weight * 7
            recommendations.append(("Adria", adria_rec, score))

        # SHOPPING - buy potions, gear upgrades (in town only)
        shopping_rec = self.shopping.evaluate(state)
        if state.get("in_town") and (not shopping_rec or shopping_rec.weight == 0.0):
            logger.info(f"🛒 Shopping agent: {shopping_rec.reasoning if shopping_rec else 'None'} (weight={shopping_rec.weight if shopping_rec else 'N/A'})")
        if shopping_rec and shopping_rec.weight > 0.0:
            # Priority 6 for shopping (buying potions is important)
            # Boost priority if low on HP potions
            belt = state.get("belt", [])
            hp_potions = sum(1 for slot in belt if slot == "hp")
            priority = 7 if hp_potions < 2 else 6
            score = shopping_rec.weight * priority
            recommendations.append(("Shopping", shopping_rec, score))

        # COMBAT - high priority if monsters nearby
        combat_rec = self.combat.evaluate(state)
        if combat_rec and combat_rec.weight > 0.0 and hp_pct > 35:
            # Priority 8 for combat, reduced if low HP
            priority = 8 if hp_pct > 50 else 6
            score = combat_rec.weight * priority
            recommendations.append(("Combat", combat_rec, score))

        # LOOT - CRITICAL priority when HP low and potions on ground
        loot_rec = self.loot.evaluate(state)
        if loot_rec and loot_rec.weight > 0.0:
            # Priority boosts:
            # - HP < 30% and potions on ground = URGENT (priority 9)
            # - HP potions < 3 in belt = HIGH (priority 6)
            # - Otherwise = MEDIUM (priority 4)
            belt = state.get("belt", [])
            hp_potions = sum(1 for slot in belt if slot == "hp")
            loot = state.get("loot", [])

            if hp_pct < 30 and loot:
                priority = 9  # CRITICAL - dying and potions on ground!
            elif hp_potions < 3:
                priority = 6  # HIGH - low on potions
            else:
                priority = 4  # MEDIUM - normal looting

            # Danger dampener: reduce looting priority when in danger (unless critical HP)
            danger_mult = 1.0 if hp_pct < 30 else (0.5 if danger > 0.5 else 1.0)
            score = loot_rec.weight * priority * danger_mult
            recommendations.append(("Loot", loot_rec, score))

        # MOVEMENT - fallback, always evaluates
        movement_rec = self.movement.evaluate(state)
        if movement_rec and movement_rec.weight > 0.0:
            # Priority 3 for movement (fallback)
            # Danger dampener: reduce exploration when in danger
            danger_mult = 0.5 if danger > 0.5 else 1.0
            score = movement_rec.weight * 3 * danger_mult
            recommendations.append(("Movement", movement_rec, score))

        # Emergency healing override - BUT coordinate with LootAgent!
        # If HP critical but no potions in belt, let LootAgent pick them up
        if hp_pct < 25 and healing_rec:
            # Check if healing actually has potions
            belt = state.get("belt", [])
            has_potions = any(slot in ["hp", "rj"] for slot in belt)

            if has_potions:
                # Detect failed US attempts (HP not changing)
                if self.last_command and self.last_command.startswith("US"):
                    if abs(hp_pct - self.last_hp) < 2:  # HP barely changed
                        self.failed_use_count += 1
                    else:
                        self.failed_use_count = 0  # Reset on success

                # If US failed 3+ times, give up and let other agents handle it
                if self.failed_use_count >= 3:
                    logger.warning(f"⚠️  US command failed {self.failed_use_count} times - deferring to agents")
                    self.failed_use_count = 0  # Reset counter
                    # Fall through to normal scoring
                else:
                    # We have potions - try using them!
                    logger.info(f"🚨 EMERGENCY HEALING: HP={hp_pct}%")
                    self.last_hp = hp_pct
                    self.last_command = healing_rec.command
                    return healing_rec.command
            else:
                # NO potions - let LootAgent or retreat take priority
                logger.info(f"🚨 EMERGENCY but NO POTIONS: HP={hp_pct}% - deferring to agents")
                # Fall through to normal scoring (LootAgent or retreat will handle)

        # Apply hysteresis: +0.15 bias to last agent if chosen within 1.5s
        # This prevents ping-ponging between similar-scoring agents
        current_time = time.time()
        if self.last_decision_agent and (current_time - self.last_decision_time) < 1.5:
            # Find the last agent in recommendations and boost its score
            for i, (agent_name, response, score) in enumerate(recommendations):
                if agent_name == self.last_decision_agent:
                    recommendations[i] = (agent_name, response, score + 0.15)
                    logger.debug(f"⏱️  Hysteresis: +0.15 bias to {agent_name} (continuity)")
                    break

        # Pick highest score
        if not recommendations:
            return "SAY Waiting..."

        best = max(recommendations, key=lambda x: x[2])
        agent_name, response, score = best

        # Track DROP commands to avoid picking them back up
        if response.command.startswith("DROP ") and not response.command.startswith("DROP GOLD"):
            # Dropped an item - mark companion's current position
            me_x, me_y, _, _ = state["me"]
            self.recently_dropped_position = (me_x, me_y)
            self.recently_dropped_tick = state.get("tick", 0)
            # Notify LootAgent to ignore items at this position
            self.loot.recently_dropped[(me_x, me_y)] = self.recently_dropped_tick
            logger.info(f"🎁 Dropped item at ({me_x},{me_y}) - LootAgent will ignore for 10 seconds")

        # Update hysteresis tracking
        self.last_decision_agent = agent_name
        self.last_decision_time = current_time

        # Debug logging
        logger.info(f"🎯 Decision: {agent_name} → {response.command} (score: {score:.2f}, weight: {response.weight:.2f})")
        if len(recommendations) > 1:
            alternatives = [(r[0], r[2]) for r in sorted(recommendations, key=lambda x: x[2], reverse=True)[1:]]
            logger.info(f"   Alternatives: {alternatives}")
        logger.debug(f"   Reasoning: {response.reasoning}")

        # Track command for failure detection
        self.last_command = response.command
        self.last_hp = hp_pct

        return response.command

    def warmup_llm(self):
        """Warm up the LLM by loading the model into memory"""
        logger.info("🔥 Warming up LLM (loading model into memory)...")
        try:
            import requests
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.dungeon_model,  # Use dungeon model for warmup
                    "prompt": "Hi",
                    "stream": False,
                    "options": {"num_predict": 1}
                },
                timeout=60.0
            )
            resp.raise_for_status()
            logger.info("✅ LLM warmed up and ready")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to warm up LLM: {e}")
            return False

    def run(self):
        """Main orchestrator loop"""
        self.connect()

        # Warm up LLM before starting
        if not self.warmup_llm():
            logger.warning("⚠️  LLM warmup failed, but continuing anyway...")

        # Start chat handler thread
        self.chat_handler.start()
        logger.info("💬 Chat handler thread started")

        logger.info("🤖 Orchestrator running! Waiting for state updates...")
        logger.info(f"💭 Think interval: {self.think_interval}s")

        state_count = 0

        try:
            while True:
                # Receive DSL message from game
                dsl_line = self.recv_message()

                if not dsl_line:
                    time.sleep(0.01)
                    continue

                # Handle chat messages
                if dsl_line.startswith("CHAT "):
                    parts = dsl_line[5:].split(": ", 1)
                    if len(parts) == 2:
                        sender, message = parts
                        logger.info(f"💬 {sender}: {message}")
                        # Queue to ChatAgent for intelligent responses with full context
                        self.chat.queue_player_message(sender, message)
                    continue

                # Parse state
                state = parse_dsl_state(dsl_line)

                if state["tick"] == 0:
                    continue  # Invalid state

                state_count += 1

                # Initialize character profile on first valid state
                if self.profile is None and state.get("stats"):
                    logger.info("🔍 Initializing character profile from first state...")
                    self.profile = CharacterProfile(state)
                    # Share profile with all agents
                    for agent in self.agents:
                        agent.profile = self.profile
                    # Share profile with chat handler
                    self.chat_handler.profile = self.profile
                elif self.profile:
                    # Update profile on state changes (level ups, etc.)
                    if self.profile.update_stats(state):
                        logger.info(f"📊 Character profile updated: {self.profile}")

                # Debug: Log raw DSL with length and NPC detection
                if state_count <= 3 or state.get("in_town"):
                    dsl_len = len(dsl_line)
                    has_npc = "NPC=" in dsl_line
                    has_store = "ST_" in dsl_line
                    logger.info(f"🔍 Raw DSL: {dsl_line[:200]}... (len={dsl_len}, NPC={has_npc}, STORE={has_store})")

                    # Show end of DSL if it's long (to see NPC/store data)
                    if dsl_len > 300:
                        logger.info(f"🔍 DSL end: ...{dsl_line[-200:]}")

                    # Log parsed state NPCs and stores
                    if has_npc or has_store:
                        npcs = state.get("npcs", [])
                        stores = state.get("stores", {})
                        logger.info(f"🔍 Parsed: NPCs={len(npcs)}, Stores={list(stores.keys())}")

                # Update chat context with latest game state
                self.chat_handler.update_context(state)

                # Log state occasionally
                if state_count % 30 == 0:
                    me_x, me_y, hp_pct, mp_pct = state["me"]
                    belt = state.get("belt", [])
                    belt_str = ",".join(belt) if belt else "empty"
                    stats = state.get("stats")
                    if stats:
                        lvl = stats['lvl']
                        exp = stats.get('exp', 0)
                        pts = stats.get('pts', 0)
                        str_val = stats.get('str', 0)
                        dex_val = stats.get('dex', 0)
                        mag_val = stats.get('mag', 0)
                        vit_val = stats.get('vit', 0)
                        stats_str = f"lvl={lvl} exp={exp} pts={pts} STR={str_val} DEX={dex_val} MAG={mag_val} VIT={vit_val}"
                    else:
                        stats_str = "no_stats"
                    town_str = "TOWN" if state.get("in_town") else f"floor={state['floor']}"
                    logger.info(
                        f"📥 State: tick={state['tick']} {town_str} {stats_str} "
                        f"pos=({me_x},{me_y}) hp={hp_pct}% mobs={len(state['mobs'])} loot={len(state['loot'])} belt=[{belt_str}]"
                    )

                # Update memory (for future agents)
                self.last_state = state

                # Update companion state in SQLite for chat queries (every 10 ticks to reduce DB writes)
                if state["tick"] % 10 == 0:
                    companion_state = prepare_companion_state_for_db(state)
                    self.memory.update_companion_state(companion_state, state["tick"])

                # Decide if we should think
                if not self.should_think():
                    continue

                self.last_think_time = time.time()

                # Get decision from council
                start_time = time.time()
                command = self.decide(state)
                decision_time = time.time() - start_time

                logger.info(f"📤 Command: {command} (took {decision_time:.2f}s)")

                # Send command back to game
                self.send_message(command)

        except KeyboardInterrupt:
            logger.info("\n👋 Orchestrator stopped by user")
        except Exception as e:
            logger.error(f"💥 Orchestrator crashed: {e}", exc_info=True)
        finally:
            self.chat_handler.stop()
            if self.sock:
                self.sock.close()
            self.memory.close()
            logger.info("🔒 Orchestrator shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="Agent Council Orchestrator for DevilutionX GAP")
    parser.add_argument("--socket", "-s", default=SOCKET_PATH, help="GAP socket path")
    parser.add_argument("--ollama-url", default=OLLAMA_URL, help="Ollama API URL")
    parser.add_argument("--model", "-m", default="qwen2.5:3b", help="Dungeon model (fast combat)")
    parser.add_argument("--chat-model", default="llama3.1:8b", help="Town/chat model (sophisticated)")
    parser.add_argument("--password", "-p", help="Game password")
    parser.add_argument("--think-interval", type=float, default=1.0, help="Seconds between decisions")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    orchestrator = AgentOrchestrator(
        socket_path=args.socket,
        ollama_url=args.ollama_url,
        model=args.model,
        chat_model=args.chat_model,
        password=args.password,
        think_interval=args.think_interval,
    )

    logger.info("=" * 60)
    logger.info("Agent Council Orchestrator")
    logger.info("=" * 60)
    logger.info(f"Socket: {args.socket}")
    logger.info(f"Dungeon model: {args.model}")
    logger.info(f"Town model: {args.chat_model}")
    logger.info(f"Think interval: {args.think_interval}s")
    logger.info("=" * 60)

    orchestrator.run()


if __name__ == "__main__":
    main()
