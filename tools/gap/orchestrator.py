#!/usr/bin/env python3
"""
Agent Council Orchestrator for DevilutionX GAP

Coordinates specialist agents to make optimal game decisions.
"""

import os
import socket
import struct
import logging
import time
import argparse
import signal
import sys
from typing import Optional, List, Tuple
from agents.base import AgentResponse
from agents.combat import CombatAgent
from agents.spell import SpellAgent
from agents.healing import HealingAgent
from agents.movement import MovementAgent
from agents.transition import TransitionAgent
from agents.portal import PortalAgent
from agents.upgrade import UpgradeAgent
from agents.loot import LootAgent
from agents.stats import StatsAgent
from agents.town import TownAgent
from agents.shopping import ShoppingAgent
from agents.inventory import InventoryAgent
from agents.griswold import GriswoldAgent
from agents.cain import CainAgent
from agents.adria import AdriaAgent
from agents.chat import ChatAgent
from agents.exploration import ExplorationAgent
from dsl_parser import parse_dsl_state
from memory_store import MemoryStore, prepare_companion_state_for_db
from personality_store import PersonalityStore
from chat_handler import ChatHandler
from character_profile import CharacterProfile

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Per-client GAP socket. The headless client derives its path from the hero save
# stem (multi_1.sv -> /tmp/devilutionx-gap-multi_1.sock) so multiple AI players
# don't collide; launch_agent.sh passes the matching --socket. The orchestrator
# computes the same path from --hero, so the two stay in sync without a magic
# literal. multi_1 is the standard player-2 hero, used when nothing is specified.
DEFAULT_HERO = "multi_1.sv"


def socket_path_for(hero: str) -> str:
    """GAP socket path for a given hero save, derived from its filename stem."""
    stem = os.path.splitext(os.path.basename(hero))[0]
    return f"/tmp/devilutionx-gap-{stem}.sock"
OLLAMA_URL = "http://localhost:11434/api/generate"


class CommitmentTracker:
    """Adds commitment/hysteresis to council voting so the companion finishes
    what it started instead of flip-flopping between similar-priority goals.

    Retains a short memory of the recent winner and nudges scores accordingly:

    - The incumbent (currently-committed) agent gets a flat ``bonus`` to its
      score, so small per-tick score wiggles can't flip the winner.
    - If the incumbent is briefly *absent* (an agent that returns weight 0 for a
      tick, e.g. the Town agent when it momentarily can't decide), low-priority
      *fallback* agents (Movement/Exploration) are damped so a transient gap in
      the committed goal doesn't make her wander off — that was the pacing bug.
    - Commitment decays: after ``max_streak`` consecutive committed rounds the
      bonus is dropped for a round so a stalled or genuinely-superseded goal can
      be replaced. High-priority agents (Healing/Combat/Chat) still win because
      ``bonus`` is smaller than their priority gap over town/movement work.
    """

    FALLBACK_AGENTS = {"Movement", "Exploration"}

    def __init__(self, bonus: float = 2.5, fallback_damp: float = 0.2, max_streak: int = 12):
        self.bonus = bonus
        self.fallback_damp = fallback_damp
        self.max_streak = max_streak
        self.incumbent: Optional[str] = None
        self.streak = 0

    def apply(self, recommendations):
        """Return recommendations with the incumbent boosted and, when the
        incumbent is missing this round, fallback agents damped."""
        if not self.incumbent or self.streak >= self.max_streak or not recommendations:
            return recommendations

        present = {name for name, _, _ in recommendations}
        incumbent_present = self.incumbent in present

        adjusted = []
        for name, response, score in recommendations:
            if name == self.incumbent:
                score += self.bonus
            elif not incumbent_present and name in self.FALLBACK_AGENTS:
                score *= self.fallback_damp
            adjusted.append((name, response, score))
        return adjusted

    def note_winner(self, agent_name: str):
        """Record the chosen agent. Staying on the same goal extends the streak;
        switching goals resets commitment to the new winner."""
        if agent_name == self.incumbent and self.streak < self.max_streak:
            self.streak += 1
        else:
            self.incumbent = agent_name
            self.streak = 0


class AgentOrchestrator:
    """Orchestrates specialist agents to make optimal decisions"""

    def __init__(
        self,
        socket_path: str = socket_path_for(DEFAULT_HERO),
        ollama_url: str = OLLAMA_URL,
        model: str = "qwen2.5:3b",
        chat_model: str = "llama3.1:8b",
        password: Optional[str] = None,
        think_interval: float = 0.6,
    ):
        self.socket_path = socket_path
        self.ollama_url = ollama_url
        self.dungeon_model = model  # Fast model for combat
        self.town_model = chat_model  # Better model for town interactions
        self.password = password
        self.think_interval = think_interval

        self.sock = None
        self.connection_closed = False  # set True when the game closes the socket (EOF)
        # Key the memory DB per client so multiple AI players (each on its own
        # socket, e.g. a Rogue on multi_1 and a Sorc on multi_2) don't clobber a
        # shared gap_memory.db. The socket stem uniquely identifies this client.
        sock_stem = os.path.splitext(os.path.basename(socket_path))[0]
        self.memory = MemoryStore(db_path=f"gap_memory_{sock_stem}.db")
        self.personality = None  # PersonalityStore (initialized after character profile is known)
        self.personality_data = {}  # Will be populated after character_id is known
        self.last_think_time = 0
        self.last_state = None
        self.current_context = None  # Track town vs dungeon for model switching
        self.profile = None  # Character profile (initialized on handshake)

        # Session statistics for end-of-session reflection
        self.session_stats = {
            "battles": 0,
            "deaths": 0,
            "victories": 0,
            "gifts_received": 0,
            "levels_cleared": 0,
            "near_deaths": 0
        }

        # Failure tracking to prevent infinite USE loops
        self.last_command = None
        self.last_hp = 100
        self.failed_use_count = 0

        # Personality tracking state
        self.in_combat = False  # Track if currently in combat
        self.combat_start_tick = 0
        self.combat_start_hp = 100
        self.lowest_hp_in_combat = 100  # Track lowest HP during combat for near-death detection

        # Hysteresis tracking to prevent ping-ponging
        self.last_decision_agent = None
        self.last_decision_time = 0
        # Commitment/hysteresis: keeps the council on one goal for several rounds
        self.commitment = CommitmentTracker()

        # Tactical stance set by the player's chat commands ("hold here", "go in",
        # "fall back", "on me"). Modulates the council so boss-fight planning works.
        self.tactical_mode = "follow"  # follow | hold | engage | retreat

        # Track recently dropped items (for mutual support)
        self.recently_dropped_position = None
        self.recently_dropped_tick = 0

        # Initialize specialist agents
        # Start with dungeon model (most common context)
        self.combat = CombatAgent(model=model, ollama_url=ollama_url)
        self.spell = SpellAgent(model=model, ollama_url=ollama_url)
        self.healing = HealingAgent(model=model, ollama_url=ollama_url)
        self.loot = LootAgent(model=model, ollama_url=ollama_url)
        self.stats = StatsAgent(model=model, ollama_url=ollama_url)
        self.town = TownAgent(model=model, ollama_url=ollama_url)
        self.shopping = ShoppingAgent(model=model, ollama_url=ollama_url)
        self.inventory = InventoryAgent(model=model, ollama_url=ollama_url)
        self.griswold = GriswoldAgent(model=model, ollama_url=ollama_url)
        self.cain = CainAgent(model=model, ollama_url=ollama_url)
        self.adria = AdriaAgent(model=model, ollama_url=ollama_url)
        self.exploration = ExplorationAgent(model=model, ollama_url=ollama_url)
        self.movement = MovementAgent(model=model, ollama_url=ollama_url)
        self.transition = TransitionAgent(model=model, ollama_url=ollama_url)
        self.portal = PortalAgent(model=model, ollama_url=ollama_url)
        self.upgrade = UpgradeAgent(model=model, ollama_url=ollama_url)
        self.chat = ChatAgent(memory=self.memory, model=chat_model, ollama_url=ollama_url)

        # List of all agents for easy model switching
        self.agents = [
            self.combat, self.spell, self.healing, self.loot,
            self.stats, self.town, self.shopping,
            self.inventory, self.griswold, self.cain, self.adria, self.exploration,
            self.upgrade, self.portal, self.transition, self.movement,
            self.chat
        ]

        # Note: Personality and profile will be injected after character_id is known (on first state)

        # Chat handler (runs in thread, non-blocking)
        self.chat_handler = ChatHandler(
            send_message_callback=self._send_message_internal,
            use_llm=True,  # Enable LLM for natural conversations
            model=chat_model,
            ollama_url=ollama_url
        )

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

        logger.info("🎯 Agent Orchestrator initialized")
        logger.info(f"  Agents: Combat, Healing, Loot, Stats, Town, Shopping, Inventory, Griswold, Cain, Adria, Movement, Chat")
        logger.info(f"  Dungeon model: {self.dungeon_model} (fast combat)")
        logger.info(f"  Town model: {self.town_model} (sophisticated interactions)")
        logger.info(f"  Think interval: {think_interval}s")
        logger.info(f"  Strategy: Context-based model switching (automatic)")
        logger.info(f"  Personality: Will initialize after character identity is known")

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

    def _shutdown_handler(self, signum, frame):
        """Graceful shutdown on Ctrl+C or SIGTERM"""
        logger.info("\n🛑 Graceful shutdown initiated...")

        try:
            # Generate session reflection if meaningful session occurred and personality initialized
            if self.personality and (self.session_stats["battles"] > 0 or self.session_stats["deaths"] > 0):
                logger.info("📖 Generating session reflection...")
                self._save_session_reflection()
            elif not self.personality:
                logger.info("📖 Personality not initialized (session too short)")
            else:
                logger.info("📖 No meaningful session to reflect on (no battles/deaths)")

            # Close database connections
            if self.personality:
                self.personality.close()
            self.memory.close()

            # Close socket
            if self.sock:
                self.sock.close()

            logger.info("✅ Shutdown complete. Personality and memories saved.")

        except Exception as e:
            logger.error(f"⚠️ Error during shutdown: {e}")
        finally:
            sys.exit(0)

    def _save_session_reflection(self):
        """Ask LLM to reflect on session before exit"""
        try:
            # Build reflection prompt
            prompt = f"""Session ending. Reflect briefly on this gameplay session:

Battles fought: {self.session_stats['battles']}
Deaths: {self.session_stats['deaths']}
Victories: {self.session_stats['victories']}
Near-death experiences: {self.session_stats['near_deaths']}
Gifts from player: {self.session_stats['gifts_received']}
Levels cleared: {self.session_stats['levels_cleared']}

In 1-2 sentences: What should you remember for next time? What did you learn?"""

            # Use chat model for reflection (better at summaries)
            import requests
            payload = {
                "model": self.town_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 100
                }
            }

            resp = requests.post(self.ollama_url, json=payload, timeout=15.0)
            resp.raise_for_status()
            reflection = resp.json().get("response", "Session complete.").strip()

            # Save reflection
            self.personality.save_session_reflection(reflection, self.session_stats)

            logger.info(f"📖 Reflection: {reflection}")

        except Exception as e:
            logger.error(f"⚠️ Failed to generate reflection: {e}")
            # Save with generic reflection
            self.personality.save_session_reflection(
                "Session complete - stats recorded.",
                self.session_stats
            )

    def recv_message(self) -> Optional[str]:
        """Receive length-prefixed message from socket"""
        try:
            length_bytes = self.sock.recv(4)
            if len(length_bytes) == 0:
                # recv() returned empty without timing out → peer (game) closed
                # the socket cleanly. Signal the run loop to shut down.
                self.connection_closed = True
                return None
            if len(length_bytes) < 4:
                return None

            length = struct.unpack('<I', length_bytes)[0]

            data = b""
            while len(data) < length:
                chunk = self.sock.recv(length - len(data))
                if not chunk:
                    self.connection_closed = True
                    return None
                data += chunk

            return data.decode('utf-8')

        except socket.timeout:
            return None
        except (ConnectionResetError, BrokenPipeError):
            # Game went away mid-stream (crash/quit) — treat as a disconnect.
            self.connection_closed = True
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

    # --- Tactical commands ------------------------------------------------
    # Concise battle directions the player can speak to coordinate fights:
    #   hold    — hold position, stop following (set up a boss pull)
    #   engage  — push the fight, prioritize attacking
    #   retreat — break off and regroup on the player
    #   follow  — resume normal following (the default stance)
    # Keyword phrases checked most-specific first; each maps to a stance + a
    # short spoken acknowledgement.
    TACTICAL_INTENTS = [
        ("hold", "Holding here.", (
            "hold position", "hold here", "hold up", "hold on", "wait here",
            "stay here", "stay put", "stay back", "hang back", "wait there",
            "hold", "wait", "stay", "stop",
        )),
        ("retreat", "Falling back!", (
            "fall back", "pull back", "back up", "back off", "get back",
            "retreat", "regroup", "disengage", "run", "flee", "bail",
        )),
        ("engage", "Going in!", (
            "go in", "get him", "get her", "get it", "take him", "take it",
            "attack", "engage", "kill it", "kill him", "push", "charge",
            "go go", "light em up", "open fire", "fire",
        )),
        ("follow", "On you.", (
            "with me", "on me", "come on", "let's go", "lets go", "move out",
            "follow me", "follow", "come", "regroup on me",
        )),
    ]

    def _detect_tactical_intent(self, message: str):
        """Return (mode, acknowledgement) if the message is a tactical command,
        else None. Commands are imperative — they LEAD the sentence — so we match
        at the start (after stripping a politeness lead-in). That keeps chatter
        like 'I follow your logic' or 'no, go ahead' from tripping a stance."""
        text = message.lower().strip().rstrip("!.?,")
        for lead in ("can you ", "could you ", "go ahead and ", "ok ", "okay ",
                     "now ", "hey ", "please ", "yo "):
            if text.startswith(lead):
                text = text[len(lead):]
                break
        words = text.split()
        for mode, ack, phrases in self.TACTICAL_INTENTS:
            for phrase in phrases:
                pw = phrase.split()
                if words[:len(pw)] == pw:
                    return mode, ack
        return None

    def _apply_tactical_mode(self, recommendations, state):
        """Modulate the council's recommendations by the current stance."""
        mode = self.tactical_mode
        if mode == "follow" or not recommendations:
            return recommendations

        if mode == "hold":
            # Don't move toward the player — hold position. Combat/heal/loot
            # still run (she'll defend herself), but follow/transition/portal are
            # suppressed and we actively stand put.
            held = [(n, r, s) for (n, r, s) in recommendations
                    if n not in ("Movement", "Transition", "Portal")]
            me_x, me_y = state["me"][0], state["me"][1]
            held.append((
                "Hold",
                AgentResponse(command=f"MV {me_x} {me_y}", weight=0.4,
                              reasoning="Hold: holding position (commanded)"),
                0.4 * 4,
            ))
            return held

        if mode == "engage":
            # Push the fight: boost offensive agents.
            return [(n, r, s * 1.4 if n in ("Combat", "Spell") else s)
                    for (n, r, s) in recommendations]

        if mode == "retreat":
            # Break off and regroup on the player; drop offensive actions.
            out = [(n, r, s) for (n, r, s) in recommendations
                   if n not in ("Combat", "Spell")]
            player = state.get("player")
            if player:
                out.append((
                    "Retreat",
                    AgentResponse(command=f"MV {player[0]} {player[1]}", weight=0.9,
                                  reasoning="Retreat: regrouping on player (commanded)"),
                    0.9 * 9,
                ))
            # Once she's regrouped (near the player and clear of mobs), drop back
            # to normal following so she doesn't stay stuck in retreat.
            me = state.get("me", [0, 0, 100, 100])
            if player and not state.get("mobs"):
                if max(abs(player[0] - me[0]), abs(player[1] - me[1])) <= 3:
                    self.tactical_mode = "follow"
            return out

        return recommendations

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
        4. SPELL (9) - Ranged magic attacks for casters
        5. CAIN (8) - Identify items before selling/using
        6. COMBAT (8/6) - Attack monsters when HP healthy
        7. INVENTORY (7) - Emergency belt refills, proactive management
        8. ADRIA (7) - Witch shop for casters (mana potions, staves, books)
        9. SHOPPING (6-7) - Buy HP potions, gear upgrades
        10. GRISWOLD (6) - Sell junk items, free inventory space
        11. TOWN (5) - Navigate to NPCs, general town activities
        12. LOOT (4-9) - Pick up items (priority varies by urgency)
        13. MOVEMENT (3) - Exploration and following player

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
            # Learned-strategy nudge: lean in where this approach has worked,
            # back off (let healing/retreat win) where it's been getting us killed.
            score *= self._combat_confidence_mult(state)
            recommendations.append(("Combat", combat_rec, score))

        # SPELL CASTING - ranged magic attacks for casters
        spell_rec = self.spell.evaluate(state)
        if spell_rec and spell_rec.weight > 0.0:
            # Priority 9 for spell casting (high priority, safer than melee)
            # Boost priority when mana is high and monsters are grouped
            priority = 9
            score = spell_rec.weight * priority
            recommendations.append(("Spell", spell_rec, score))

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

            # Gold-pickup boost: when she's gold-constrained and there's gold on
            # the ground, grab it before fixating on something she can't yet afford
            # (e.g. an unaffordable Griswold repair while ignoring dropped gold).
            gold_on_ground = any(item.get("type") == "go" for item in loot)
            if gold_on_ground:
                # Gold is almost always worth grabbing — prioritize it over town
                # chores and following (but still below active combat, priority 8).
                priority = max(priority, 7)

            # Danger dampener: reduce looting priority when in danger (unless critical HP)
            danger_mult = 1.0 if hp_pct < 30 else (0.5 if danger > 0.5 else 1.0)
            score = loot_rec.weight * priority * danger_mult
            recommendations.append(("Loot", loot_rec, score))

        # EXPLORATION - open chests, doors, barrels (priority 4, between loot and movement)
        exploration_rec = self.exploration.evaluate(state)
        if exploration_rec and exploration_rec.weight > 0.0:
            # Priority 4 for exploration (chests/doors/barrels)
            # Dampened when in danger (don't open chests while surrounded)
            danger_mult = 0.3 if danger > 0.6 else 1.0
            score = exploration_rec.weight * 4 * danger_mult
            recommendations.append(("Exploration", exploration_rec, score))

        # UPGRADE - swap in better gear when she's safe (priority 6, like town
        # chores). One-shot: once equipped, find_upgrades stops returning it.
        upgrade_rec = self.upgrade.evaluate(state)
        if upgrade_rec and upgrade_rec.weight > 0.0:
            score = upgrade_rec.weight * 6
            recommendations.append(("Upgrade", upgrade_rec, score))

        # PORTAL - follow through the player's town portal (preferred over stairs
        # when one exists; she must rush before the caster closes it).
        portal_rec = self.portal.evaluate(state)
        if portal_rec and portal_rec.weight > 0.0:
            score = portal_rec.weight * 7
            recommendations.append(("Portal", portal_rec, score))

        # TRANSITION - follow the player across floors via stairs (beats town
        # chores/wandering, but not combat/healing).
        transition_rec = self.transition.evaluate(state)
        if transition_rec and transition_rec.weight > 0.0:
            score = transition_rec.weight * 6
            recommendations.append(("Transition", transition_rec, score))

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

        # Grab valuable loot before anything but survival: a strong Loot pick
        # pre-empts town chores, following, transitions and portals so she
        # actually picks up a magic find in front of her (commitment otherwise
        # walks her right past it, and a Pepin visit out-scores it). Combat /
        # Healing / Spell still win — survival first. Loot's 3-strike blacklist
        # releases anything unreachable, so this can't deadlock.
        loot_score = max((s for (n, _r, s) in recommendations if n == "Loot"), default=0)
        if loot_score >= 5.0:
            keep = {"Combat", "Healing", "Spell", "Loot"}
            recommendations = [(n, r, s) for (n, r, s) in recommendations if n in keep]

        # Apply the player's tactical stance (hold/engage/retreat) before
        # hysteresis so the commanded behavior shapes the vote.
        recommendations = self._apply_tactical_mode(recommendations, state)

        # Apply commitment/hysteresis: boost the goal we're already committed to
        # and damp fallback agents during a transient gap, so she finishes a goal
        # instead of pacing between (e.g.) walking to Pepin and following you.
        current_time = time.time()
        recommendations = self.commitment.apply(recommendations)

        # Pick highest score
        if not recommendations:
            return "SAY Waiting..."

        best = max(recommendations, key=lambda x: x[2])
        agent_name, response, score = best

        # Record the winner so commitment persists to the next round
        self.commitment.note_winner(agent_name)

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

        # Track personality-relevant events
        self._track_personality_events(state, agent_name, response.command, hp_pct)

        # Track command for failure detection
        self.last_command = response.command
        self.last_hp = hp_pct

        return response.command

    def _combat_strategy_label(self) -> str:
        """Coarse combat approach for strategy learning, from the class playstyle."""
        ps = (self.profile.playstyle if self.profile else "") or ""
        if "ranged" in ps:
            return "ranged"
        if "melee" in ps:
            return "melee"
        if "caster" in ps or "mage" in ps or "spell" in ps:
            return "spell"
        return ps or "engage"

    def _combat_confidence_mult(self, state: dict) -> float:
        """Weight multiplier for Combat based on how the class's approach has
        fared on this floor. >1 where it's been winning, <1 where it's been
        dying — so memory actually shifts behavior. Neutral until there's
        enough evidence."""
        if not self.personality or not self.profile:
            return 1.0
        floor = state.get("floor", 0)
        confidence, attempts = self.personality.get_strategy_confidence(
            f"combat_floor_{floor}", self._combat_strategy_label()
        )
        if confidence is None or attempts < 2:
            return 1.0  # not enough evidence yet
        if confidence >= 0.7:
            return 1.1   # proven here — lean in
        if confidence <= 0.34:
            return 0.7   # been getting killed here — be cautious
        return 1.0

    def _track_personality_events(self, state: dict, agent_name: str, command: str, hp_pct: int):
        """Track personality-relevant events (combat, near-deaths, victories, gifts)"""
        mobs = state.get("mobs", [])
        floor = state.get("floor", 0)
        tick = state.get("tick", 0)
        me_x, me_y, _, _ = state["me"]

        # Combat tracking
        if mobs and not self.in_combat:
            # Combat started
            self.in_combat = True
            self.combat_start_tick = tick
            self.combat_start_hp = hp_pct
            self.lowest_hp_in_combat = hp_pct
            self.session_stats["battles"] += 1
            logger.debug(f"⚔️  Combat started (HP: {hp_pct}%)")

        elif self.in_combat:
            # Currently in combat - track lowest HP
            if hp_pct < self.lowest_hp_in_combat:
                self.lowest_hp_in_combat = hp_pct

            # Check for death (HP dropped to 0 or very low)
            if hp_pct <= 5 and self.last_hp > 5:
                self.session_stats["deaths"] += 1
                self.personality.add_memory(
                    memory_type="death",
                    description=f"Died in combat on floor {floor}",
                    emotional_impact=-0.9,
                    location=f"level_{floor}",
                    actor="monster",
                    context={"hp_before": self.last_hp, "tick": tick}
                )
                # Learning: this approach failed on this floor.
                self.personality.add_strategy(
                    f"combat_floor_{floor}", self._combat_strategy_label(), success=False
                )
                logger.info(f"💀 Death recorded (floor {floor})")

            # Check for near-death experience (survived below 25% HP)
            elif self.lowest_hp_in_combat < 25 and hp_pct > 30:
                self.session_stats["near_deaths"] += 1
                logger.debug(f"😰 Near-death: survived at {self.lowest_hp_in_combat}% HP")

            # Combat ended (no more monsters)
            if not mobs:
                self.in_combat = False
                combat_duration = tick - self.combat_start_tick

                # Victory if we survived
                if hp_pct > 5:
                    self.session_stats["victories"] += 1

                    # Learning: this approach worked on this floor.
                    self.personality.add_strategy(
                        f"combat_floor_{floor}", self._combat_strategy_label(), success=True
                    )

                    # Record memorable victories (either long fights or close calls)
                    if combat_duration > 100 or self.lowest_hp_in_combat < 40:
                        impact = 0.7 if self.lowest_hp_in_combat < 25 else 0.5
                        self.personality.add_memory(
                            memory_type="victory",
                            description=f"Won tough battle on floor {floor} (lowest HP: {self.lowest_hp_in_combat}%)",
                            emotional_impact=impact,
                            location=f"level_{floor}",
                            actor="self",
                            context={
                                "duration_ticks": combat_duration,
                                "lowest_hp": self.lowest_hp_in_combat,
                                "start_hp": self.combat_start_hp
                            }
                        )
                        logger.info(f"🏆 Victory recorded (floor {floor}, lowest HP: {self.lowest_hp_in_combat}%)")

                logger.debug(f"⚔️  Combat ended (duration: {combat_duration} ticks)")

        # Track gifts from player (DROP commands via chat)
        if command.startswith("DROP ") and not command.startswith("DROP GOLD"):
            # This is a response to player request - it's a gift
            self.session_stats["gifts_received"] += 1
            self.personality.add_memory(
                memory_type="gift",
                description=f"Received item from player on floor {floor}",
                emotional_impact=0.8,
                location=f"level_{floor}" if floor > 0 else "town",
                actor="Player",
                context={"command": command, "tick": tick}
            )
            logger.debug(f"🎁 Gift memory recorded")

    def warmup_llm(self):
        """
        Warm up the LLM by loading the model into memory.

        This is done BEFORE connecting to the game to eliminate the initial lag
        that happens when the companion first spawns. The first LLM inference can
        take several seconds (model loading), which would cause the companion to
        stand idle. By warming up first, the companion responds immediately.
        """
        logger.info("🔥 Warming up LLM (loading model into memory)...")
        logger.info("   This prevents initial lag when companion spawns...")
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
            logger.info("✅ LLM warmed up and ready - companion will be responsive immediately")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to warm up LLM: {e}")
            return False

    def run(self):
        """Main orchestrator loop"""
        # Warm up LLM BEFORE connecting (avoids initial lag when companion joins)
        if not self.warmup_llm():
            logger.warning("⚠️  LLM warmup failed, but continuing anyway...")

        # Connect to game (this triggers companion spawn/join)
        self.connect()

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

                if self.connection_closed:
                    logger.info("🔌 Game closed the connection — shutting down gracefully.")
                    self._shutdown_handler(None, None)  # saves reflection, then exits

                if not dsl_line:
                    time.sleep(0.01)
                    continue

                # Handle chat messages
                if dsl_line.startswith("CHAT "):
                    parts = dsl_line[5:].split(": ", 1)
                    if len(parts) == 2:
                        sender, message = parts
                        logger.info(f"💬 {sender}: {message}")
                        # Tactical command? Set the stance + acknowledge. Otherwise
                        # hand off to the ChatAgent for a conversational reply.
                        intent = self._detect_tactical_intent(message)
                        if intent:
                            mode, ack = intent
                            self.tactical_mode = mode
                            logger.info(f"🎖️  Tactical stance → {mode} (from '{message}')")
                            self.send_message(f"SAY {ack}")
                        else:
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

                    # Initialize personality store with character-specific ID
                    character_id = f"{self.profile.class_name}_{self.profile.level}"
                    logger.info(f"📚 Initializing PersonalityStore for {character_id}")
                    self.personality = PersonalityStore(character_id=character_id)
                    self.personality_data = self.personality.load_personality()

                    # Share profile and personality with all agents
                    for agent in self.agents:
                        agent.profile = self.profile
                        agent.personality = self.personality

                    # Share profile and personality with chat handler
                    self.chat_handler.profile = self.profile
                    self.chat_handler.personality = self.personality
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
    parser.add_argument("--hero", default=DEFAULT_HERO, help="Hero save this agent drives (e.g. multi_2.sv); sets the default socket")
    parser.add_argument("--socket", "-s", default=None, help="GAP socket path (default: derived from --hero)")
    parser.add_argument("--ollama-url", default=OLLAMA_URL, help="Ollama API URL")
    parser.add_argument("--model", "-m", default="qwen2.5:3b", help="Dungeon model (fast combat)")
    parser.add_argument("--chat-model", default="llama3.1:8b", help="Town/chat model (sophisticated)")
    parser.add_argument("--password", "-p", help="Game password")
    parser.add_argument("--think-interval", type=float, default=0.6, help="Seconds between decisions")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # An explicit --socket wins; otherwise derive it from --hero so the agent
    # connects to the matching headless client's socket.
    socket_path = args.socket or socket_path_for(args.hero)

    orchestrator = AgentOrchestrator(
        socket_path=socket_path,
        ollama_url=args.ollama_url,
        model=args.model,
        chat_model=args.chat_model,
        password=args.password,
        think_interval=args.think_interval,
    )

    logger.info("=" * 60)
    logger.info("Agent Council Orchestrator")
    logger.info("=" * 60)
    logger.info(f"Socket: {socket_path}")
    logger.info(f"Dungeon model: {args.model}")
    logger.info(f"Town model: {args.chat_model}")
    logger.info(f"Think interval: {args.think_interval}s")
    logger.info("=" * 60)

    orchestrator.run()


if __name__ == "__main__":
    main()
