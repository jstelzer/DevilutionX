"""
Chat Agent - Reactive and proactive communication
"""

import logging
import queue
from typing import Dict, Any, Optional
from .base import BaseAgent, AgentResponse

logger = logging.getLogger(__name__)


class ChatAgent(BaseAgent):
    """Specialist for bidirectional communication with player"""

    def __init__(self, memory, **kwargs):
        super().__init__(name="Chat", **kwargs)
        self.memory = memory  # MemoryStore instance
        self.message_queue = queue.Queue()  # Player messages
        self.pending_responses = queue.Queue()  # Multi-part responses
        self.last_proactive_message = 0  # Tick of last proactive message

    def query_llm_chat(self, prompt: str) -> str:
        """
        Query LLM for chat responses with higher token limit.
        Chat needs 2-3 sentence responses (~100-150 tokens) vs combat's 20 tokens.
        """
        import requests

        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "30m",  # Keep chat model resident in VRAM between messages
                "options": {
                    "temperature": 0.7,  # More creative for chat
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_predict": 100,  # Allow 2-3 sentence responses (vs 20 for combat)
                }
            }

            # Chat is latency-tolerant; a 12B may take >10s on cold load, so allow ample time.
            resp = requests.post(self.ollama_url, json=payload, timeout=60.0)
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"Chat LLM query failed: {e}")
            return "..."

    def queue_player_message(self, sender: str, message: str):
        """Queue a message from the player for processing"""
        if sender == "player":
            self.message_queue.put((sender, message))
            logger.info(f"💬 Queued chat from {sender}: {message}")

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Activate if:
        1. Player sent a message (reactive)
        2. Something worth mentioning (proactive)
        """
        # Reactive: Player sent a message
        if not self.message_queue.empty():
            return True

        # Proactive: Check if companion should initiate conversation
        return self._has_proactive_trigger(state)

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Handle communication:
        - Pending: Send queued multi-part responses first
        - Reactive: Answer player questions using SQLite state
        - Proactive: Express needs based on game state
        """
        # Priority 0: Send pending multi-part responses
        if not self.pending_responses.empty():
            try:
                response_text = self.pending_responses.get_nowait()
                logger.info(f"💬 Continuing response: {response_text}")
                return AgentResponse(
                    command=f"SAY {response_text}",
                    weight=0.6,  # High priority - finish sending response
                    reasoning="Chat: Multi-part response continuation"
                )
            except queue.Empty:
                pass

        # Priority 1: Reactive chat (player asked a question)
        if not self.message_queue.empty():
            return self._handle_player_message(state)

        # Priority 2: Proactive chat (companion initiates)
        return self._generate_proactive_message(state)

    def _handle_player_message(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """Answer player question using SQLite companion state"""
        try:
            sender, message = self.message_queue.get_nowait()
        except queue.Empty:
            return None

        logger.info(f"💬 Processing message from {sender}: {message}")

        # Query SQLite for current companion state
        companion_state = self.memory.get_companion_state()
        if not companion_state:
            logger.warning("Chat: No companion state in DB yet")
            return AgentResponse(
                command="SAY Give me a moment, just getting my bearings...",
                weight=0.6,  # High priority - respond to player
                reasoning="Chat: No state available yet"
            )

        # Get character profile for class info
        class_names = ["Warrior", "Rogue", "Sorcerer", "Monk", "Bard", "Barbarian"]
        class_name = class_names[companion_state['class']] if companion_state['class'] < 6 else "Adventurer"

        # Check for item requests first (higher priority than chat)
        item_request = self._detect_item_request(message, companion_state, state)
        if item_request:
            return item_request

        # Build comprehensive context from SQLite
        context = self._build_context(companion_state, class_name, state)

        # Build prompt for LLM
        prompt = f"""{context}

Player asks: "{message}"

Answer naturally and concisely (1-2 sentences). Be helpful but casual. Use the information above to give accurate answers. If they ask about equipment, inventory, stats, or status - use the exact numbers provided.

Examples:
- Q: "What weapon are you using?" A: "I'm wielding a {companion_state.get('weapon_left', 'nothing right now')}."
- Q: "How many potions do you have?" A: "I've got {companion_state['hp_potions']} HP potions ready to go."
- Q: "What level are you?" A: "Level {companion_state['level']} {class_name}."
"""

        # Query LLM for natural response (allow longer chat responses)
        response = self.query_llm_chat(prompt)

        # Clean up response
        response = self._clean_response(response)

        # Store in chat history
        self.memory.add_chat_message(state['tick'], sender, message, response)

        logger.info(f"💬 Response: {response}")

        return AgentResponse(
            command=f"SAY {response}",
            weight=0.6,  # High priority - player deserves immediate response
            reasoning=f"Chat: Answer '{message[:30]}...'"
        )

    def _build_context(self, companion_state: Dict[str, Any], class_name: str, game_state: Dict[str, Any]) -> str:
        """Build comprehensive context string from companion state"""
        weapon_left = companion_state.get('weapon_left', 'nothing')
        weapon_right = companion_state.get('weapon_right', 'nothing')
        armor = companion_state.get('armor', 'nothing')
        helm = companion_state.get('helm', 'nothing')

        hp_potions = companion_state['hp_potions']
        mp_potions = companion_state['mp_potions']
        scrolls = companion_state['scrolls']
        gold = companion_state['gold']
        inv_count = companion_state['inventory_count']

        level = companion_state['level']
        experience = companion_state['experience']
        stat_points = companion_state['stat_points']

        floor = companion_state['floor']
        in_town = companion_state['in_town'] == 1

        # Get current HP/MP from game state
        me = game_state.get("me", [0, 0, 100, 100])
        hp_pct = me[2]
        mp_pct = me[3]

        context = f"""You're a level {level} {class_name} adventurer.

EQUIPMENT:
- Left Hand: {weapon_left if weapon_left else 'Empty'}
- Right Hand: {weapon_right if weapon_right else 'Empty'}
- Armor: {armor if armor else 'None'}
- Helm: {helm if helm else 'None'}

INVENTORY:
- HP Potions: {hp_potions}
- MP Potions: {mp_potions}
- Scrolls: {scrolls}
- Gold: {gold}
- Carrying: {inv_count}/40 items

STATS:
- Level: {level}
- Experience: {experience}
- Unspent stat points: {stat_points}
- Current HP: {hp_pct}%
- Current MP: {mp_pct}%

LOCATION:
- {'Town (safe)' if in_town else f'Dungeon level {floor}'}
"""

        # Weave in remembered personality so replies reflect who she's become.
        if self.personality is not None:
            try:
                memory_ctx = self.personality.get_behavioral_context(self.name)
                if memory_ctx:
                    context += f"\n{memory_ctx}\n"
            except Exception as e:
                logger.debug(f"Chat: personality context unavailable: {e}")

        return context

    def _clean_response(self, response: str) -> str:
        """Clean up LLM response artifacts and split long messages"""
        # Remove quotes
        response = response.replace('"', '').replace("'", "")

        # Remove common prefixes
        prefixes = ["A: ", "Answer: ", "Response: "]
        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix):]

        # Capitalize first letter
        if response:
            response = response[0].upper() + response[1:]

        response = response.strip()

        # Split long messages into chunks at sentence boundaries
        if len(response) > 150:
            chunks = self._split_message(response)
            if len(chunks) > 1:
                # Queue additional chunks for subsequent sends
                for chunk in chunks[1:]:
                    self.pending_responses.put(chunk)
                logger.info(f"💬 Split into {len(chunks)} parts")
                return chunks[0]

        return response

    def _split_message(self, text: str, max_length: int = 150) -> list:
        """Split text into chunks at sentence boundaries"""
        chunks = []
        current = ""

        # Split on sentence boundaries
        import re
        sentences = re.split(r'([.!?]+\s+)', text)

        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            punctuation = sentences[i + 1] if i + 1 < len(sentences) else ""
            full_sentence = sentence + punctuation

            # If adding this sentence exceeds max length, start new chunk
            if current and len(current + full_sentence) > max_length:
                chunks.append(current.strip())
                current = full_sentence
            else:
                current += full_sentence

        # Add final chunk
        if current.strip():
            chunks.append(current.strip())

        return chunks if chunks else [text]

    def _detect_item_request(self, message: str, companion_state: Dict[str, Any], game_state: Dict[str, Any]) -> Optional[AgentResponse]:
        """Detect if player is requesting an item and handle it"""
        message_lower = message.lower()

        # Detect potion requests
        potion_keywords = ['potion', 'pot', 'heal', 'healing', 'health', 'hp']
        request_keywords = ['give', 'drop', 'share', 'spare', 'can i get', 'can i have', 'need', 'want']

        # Check if message contains both request and potion keywords
        has_request = any(keyword in message_lower for keyword in request_keywords)
        wants_hp_potion = any(keyword in message_lower for keyword in potion_keywords)
        wants_mana_potion = 'mana' in message_lower or 'mp' in message_lower or 'magic' in message_lower

        # Check for gold requests
        wants_gold = 'gold' in message_lower or 'gp' in message_lower or 'coin' in message_lower

        if has_request and wants_hp_potion:
            # Find HP potion in inventory
            inventory = game_state.get("inventory", [])
            hp_potion = next((item for item in inventory if item["type"] in ["hp", "rj"]), None)

            if hp_potion:
                slot = hp_potion["slot"]
                potion_name = "healing potion" if hp_potion["type"] == "hp" else "rejuvenation potion"
                logger.info(f"💊 Dropping {potion_name} from slot {slot}")

                # Queue the chat response for next tick
                self.pending_responses.put(f"Sure! Dropping a {potion_name} for you now.")

                return AgentResponse(
                    command=f"DROP {slot}",
                    weight=0.8,  # High priority - player needs help
                    reasoning=f"Chat: Dropping HP potion from slot {slot}"
                )
            else:
                return AgentResponse(
                    command="SAY Sorry, I'm all out of healing potions!",
                    weight=0.6,  # High priority - respond to player request
                    reasoning="Chat: Player requested HP potion but we have none"
                )

        elif has_request and wants_mana_potion:
            # Find mana potion in inventory
            inventory = game_state.get("inventory", [])
            mp_potion = next((item for item in inventory if item["type"] == "mp"), None)

            if mp_potion:
                slot = mp_potion["slot"]
                logger.info(f"🔮 Dropping mana potion from slot {slot}")

                # Queue the chat response for next tick
                self.pending_responses.put("Sure! Dropping a mana potion for you.")

                return AgentResponse(
                    command=f"DROP {slot}",
                    weight=0.8,
                    reasoning=f"Chat: Dropping MP potion from slot {slot}"
                )
            else:
                return AgentResponse(
                    command="SAY Sorry, no mana potions on me right now.",
                    weight=0.6,  # High priority - respond to player request
                    reasoning="Chat: Player requested MP potion but we have none"
                )

        elif has_request and wants_gold:
            gold = companion_state.get('gold', 0)
            if gold >= 100:
                # Drop a small amount of gold
                drop_amount = min(1000, gold // 2)  # Drop up to 1000 or half our gold
                logger.info(f"💰 Player requested gold, dropping {drop_amount} (we have {gold})")

                # Queue the chat response for next tick
                self.pending_responses.put(f"Here's {drop_amount} gold - spend it wisely!")

                return AgentResponse(
                    command=f"DROP GOLD {drop_amount}",
                    weight=0.6,
                    reasoning=f"Chat: Dropping {drop_amount} gold for player"
                )
            else:
                return AgentResponse(
                    command=f"SAY I'm broke! Only got {gold} gold on me.",
                    weight=0.6,  # High priority - respond to player request
                    reasoning="Chat: Player requested gold but we don't have much"
                )

        # No item request detected
        return None

    # ============================================================================
    # PROACTIVE MESSAGING (Phase 3)
    # ============================================================================

    def _has_proactive_trigger(self, state: Dict[str, Any]) -> bool:
        """Check if something is worth mentioning proactively"""
        # Urgent triggers (always communicate)
        if self._no_belt_potions_low_hp(state):
            return True
        if self._completely_out_of_potions(state):
            return True

        # Important triggers (30s cooldown)
        tick = state.get("tick", 0)
        if tick - self.last_proactive_message >= 600:  # 30 seconds at 20 ticks/sec
            if self._low_on_potions(state):
                return True
            if self._inventory_full(state):
                return True

        # FYI triggers (60s cooldown)
        if tick - self.last_proactive_message >= 1200:  # 60 seconds
            if self._just_leveled_up(state):
                return True

        return False

    def _generate_proactive_message(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """Generate appropriate proactive message based on triggers"""
        tick = state.get("tick", 0)

        # URGENT: No belt potions + low HP (weight 0.8, no cooldown)
        if self._no_belt_potions_low_hp(state):
            message = self._generate_belt_warning(state)
            if message:
                self.last_proactive_message = tick
                return AgentResponse(
                    command=f"SAY {message}",
                    weight=0.8,  # High priority - urgent warning
                    reasoning="Chat: URGENT - No belt potions + low HP"
                )

        # URGENT: Completely out of potions (weight 0.8, no cooldown)
        if self._completely_out_of_potions(state):
            message = self._generate_out_of_potions_warning(state)
            if message:
                self.last_proactive_message = tick
                return AgentResponse(
                    command=f"SAY {message}",
                    weight=0.8,
                    reasoning="Chat: URGENT - Out of HP potions"
                )

        # Check cooldown for non-urgent messages
        if tick - self.last_proactive_message < 600:  # 30s cooldown
            return None

        # IMPORTANT: Low on potions (weight 0.5, 30s cooldown)
        if self._low_on_potions(state):
            message = self._generate_low_potions_warning(state)
            if message:
                self.last_proactive_message = tick
                return AgentResponse(
                    command=f"SAY {message}",
                    weight=0.5,
                    reasoning="Chat: Low on potions warning"
                )

        # IMPORTANT: Inventory full (weight 0.5, 30s cooldown)
        if self._inventory_full(state):
            inv_count = state.get("inv_count", 0)
            message = f"My pack's completely full ({inv_count}/40). Can't pick up any more loot!"
            self.last_proactive_message = tick
            return AgentResponse(
                command=f"SAY {message}",
                weight=0.5,
                reasoning="Chat: Inventory full warning"
            )

        # Check 60s cooldown for FYI messages
        if tick - self.last_proactive_message < 1200:
            return None

        # FYI: Just leveled up (weight 0.2, 60s cooldown)
        if self._just_leveled_up(state):
            companion_state = self.memory.get_companion_state()
            if companion_state:
                level = companion_state['level']
                stat_points = companion_state['stat_points']
                message = f"Hey! Just hit level {level}. Got {stat_points} stat points to spend!"
                self.last_proactive_message = tick
                return AgentResponse(
                    command=f"SAY {message}",
                    weight=0.2,
                    reasoning="Chat: Level up notification"
                )

        return None

    # ============================================================================
    # TRIGGER DETECTION HELPERS
    # ============================================================================

    def _no_belt_potions_low_hp(self, state: Dict[str, Any]) -> bool:
        """Detect: No HP potions in belt + low HP (URGENT!)"""
        me = state.get("me", [0, 0, 100, 100])
        hp_pct = me[2]

        # Count HP potions in belt
        belt = state.get("belt", [])
        hp_in_belt = sum(1 for item in belt if item == "hp")

        # URGENT if HP < 30% and no potions in belt
        return hp_pct < 30 and hp_in_belt == 0

    def _completely_out_of_potions(self, state: Dict[str, Any]) -> bool:
        """Detect: No HP potions anywhere (URGENT!)"""
        companion_state = self.memory.get_companion_state()
        if companion_state:
            return companion_state['hp_potions'] == 0
        return False

    def _low_on_potions(self, state: Dict[str, Any]) -> bool:
        """Detect: Low on HP potions (<4 total)"""
        companion_state = self.memory.get_companion_state()
        if companion_state:
            return 0 < companion_state['hp_potions'] < 4
        return False

    def _inventory_full(self, state: Dict[str, Any]) -> bool:
        """Detect: Inventory completely full (40/40)"""
        inv_count = state.get("inv_count", 0)
        return inv_count >= 40

    def _just_leveled_up(self, state: Dict[str, Any]) -> bool:
        """Detect: Just gained a level (has unspent stat points)"""
        companion_state = self.memory.get_companion_state()
        if companion_state:
            return companion_state['stat_points'] > 0
        return False

    # ============================================================================
    # MESSAGE GENERATION HELPERS
    # ============================================================================

    def _generate_belt_warning(self, state: Dict[str, Any]) -> Optional[str]:
        """Generate urgent warning about empty belt + low HP"""
        me = state.get("me", [0, 0, 100, 100])
        hp_pct = me[2]

        companion_state = self.memory.get_companion_state()
        if not companion_state:
            return None

        hp_potions = companion_state['hp_potions']

        if hp_potions > 0:
            # Has potions in inventory but not in belt
            return f"CRITICAL! I'm at {hp_pct}% HP with NO potions in my belt! I've got {hp_potions} in my pack but can't use them in combat. Need to refill my belt NOW!"
        else:
            # Completely out of potions
            return f"CRITICAL! I'm at {hp_pct}% HP and completely out of healing potions! Need to get to town ASAP!"

    def _generate_out_of_potions_warning(self, state: Dict[str, Any]) -> str:
        """Generate warning about being completely out of potions"""
        return "I'm completely out of healing potions! We should head to town soon."

    def _generate_low_potions_warning(self, state: Dict[str, Any]) -> str:
        """Generate warning about low potion count"""
        companion_state = self.memory.get_companion_state()
        if companion_state:
            hp_potions = companion_state['hp_potions']
            return f"Running low on healing potions - only got {hp_potions} left. Might want to stock up soon."
        return "Getting low on healing potions."
