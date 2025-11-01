#!/usr/bin/env python3
"""
Separate chat handler thread for instant, non-blocking responses.

Keeps combat decisions fast by handling chat asynchronously.
Uses templates for common phrases + optional LLM for natural responses.
"""

import threading
import queue
import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Template responses for instant replies (no LLM needed)
CHAT_TEMPLATES = {
    # Greetings
    r"hello|hi|hey|sup|yo": [
        "Hey!",
        "Hi there!",
        "Yo!",
        "What's up?",
        "Heya!",
    ],

    # Status questions
    r"how are you|you ok|you good": [
        "Still breathing!",
        "Could use a potion, but I'm good",
        "Hanging in there!",
        "Living the dream!",
        "Better than the zombies, that's for sure",
    ],

    # Combat requests
    r"attack|fight|kill|engage": [
        "On it!",
        "With pleasure!",
        "Let's dance!",
        "Time to party!",
        "Say no more!",
    ],

    # Movement requests
    r"follow|come|move|here": [
        "Coming!",
        "Right behind you",
        "On my way!",
        "Lead the way!",
    ],

    # Affirmatives
    r"thanks|thank you|good|nice|great": [
        "Anytime!",
        "No sweat!",
        "You got it!",
        "We make a good team!",
        "That's what I'm here for!",
    ],

    # Questions about readiness
    r"ready|prepared|set": [
        "Born ready!",
        "Let's do this!",
        "Ready as I'll ever be",
        "Bring it on!",
    ],

    # Fallback friendly responses - now more personality
    r".*": [  # Catch-all - use LLM instead when enabled
        "Hmm?",
        "What's that?",
        "Yeah?",
        "I hear ya",
    ],
}


class ChatHandler:
    """
    Async chat response handler.

    Runs in separate thread, responds instantly with templates.
    Optionally uses cheap LLM for complex messages.
    """

    def __init__(self, send_message_callback, use_llm: bool = True, model: str = "llama3.1:8b", ollama_url: str = "http://localhost:11434/api/generate"):
        self.send_message = send_message_callback
        self.use_llm = use_llm
        self.model = model
        self.ollama_url = ollama_url

        self.chat_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.game_context = {}  # Store latest game state for context

        logger.info(f"ChatHandler initialized (LLM: {use_llm}, model: {model})")

    def start(self):
        """Start the chat handler thread"""
        self.running = True
        self.thread = threading.Thread(target=self._chat_loop, daemon=True)
        self.thread.start()
        logger.info("Chat handler thread started")

    def stop(self):
        """Stop the chat handler thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def update_context(self, state: dict):
        """Update game context for LLM responses"""
        self.game_context = {
            "hp_pct": state.get("me", [0, 0, 100, 100])[2],
            "mp_pct": state.get("me", [0, 0, 100, 100])[3],
            "in_town": state.get("in_town", False),
            "floor": state.get("floor", 0),
            "mobs_nearby": len(state.get("mobs", [])),
            "stats": state.get("stats"),
        }

    def handle_chat(self, sender: str, message: str):
        """Queue a chat message for async handling"""
        if sender == "player":
            self.chat_queue.put((sender, message))
            logger.info(f"💬 Queued chat: {sender}: {message}")

    def _chat_loop(self):
        """Main chat processing loop (runs in thread)"""
        import re

        while self.running:
            try:
                # Wait for chat message (blocking, 100ms timeout)
                sender, message = self.chat_queue.get(timeout=0.1)

                # Find matching template
                response = self._get_template_response(message)

                # If no good template match and LLM enabled, use LLM
                if self.use_llm and not response:
                    response = self._get_llm_response(message)

                # Send response
                if response:
                    self.send_message(f"SAY {response}")
                    logger.info(f"💬 Chat response: {response}")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Chat handler error: {e}")

    def _get_template_response(self, message: str) -> Optional[str]:
        """Match message against templates and return response"""
        import re

        message_lower = message.lower().strip()

        # Try each pattern in order
        for pattern, responses in CHAT_TEMPLATES.items():
            if re.search(pattern, message_lower):
                # Don't use catch-all (.*) unless no other match
                if pattern == ".*":
                    continue
                return random.choice(responses)

        # Use catch-all if nothing else matched
        return random.choice(CHAT_TEMPLATES[".*"])

    def _get_llm_response(self, message: str) -> Optional[str]:
        """Use LLM for natural, context-aware response"""
        try:
            import requests

            # Build context string
            ctx = self.game_context
            context_str = ""
            if ctx:
                location = "in town" if ctx.get("in_town") else f"in dungeon (floor {ctx.get('floor', 0)})"
                combat_status = f"{ctx.get('mobs_nearby', 0)} monsters nearby" if ctx.get("mobs_nearby", 0) > 0 else "safe"
                context_str = f"You're {location}, {combat_status}. HP: {ctx.get('hp_pct', 100)}%."

            # Natural conversation prompt - relaxed personality
            prompt = f"""You're an adventurer fighting through Diablo's dungeons with your friend. You're brave but not reckless, helpful but not a servant. You have opinions, crack jokes, and aren't afraid to be sarcastic when things get rough. You talk like a real person, not a formal assistant.

Current situation: {context_str}

Your friend says: "{message}"

Reply naturally like you're chatting between fights. Keep it short (1-2 sentences). Be yourself - casual, genuine, maybe a little snarky. No need to be overly helpful or polite."""

            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.9,  # More creative/varied
                        "num_predict": 100,  # Room for personality
                        "top_p": 0.95,  # More diverse word choices
                    }
                },
                timeout=5.0  # Longer timeout for better model
            )

            if resp.ok:
                response = resp.json()["response"].strip()
                # Clean up common artifacts and formal language
                response = response.replace('"', '').replace("'", "")
                # Remove overly formal starts
                for prefix in ["Ah, ", "Well, ", "Indeed, ", "Certainly, ", "Of course, "]:
                    if response.startswith(prefix):
                        response = response[len(prefix):]
                # Capitalize first letter after cleanup
                if response:
                    response = response[0].upper() + response[1:]
                return response[:250]  # Cap at 250 chars for more natural responses

        except Exception as e:
            logger.warning(f"LLM chat failed: {e}")

        return None


if __name__ == "__main__":
    # Test chat templates
    logging.basicConfig(level=logging.INFO)

    def mock_send(msg):
        print(f"SEND: {msg}")

    handler = ChatHandler(mock_send, use_llm=False)
    handler.start()

    # Test messages
    test_messages = [
        "hello",
        "how are you?",
        "attack that monster",
        "follow me",
        "thanks",
        "ready?",
        "what's your favorite color?",  # Fallback
    ]

    for msg in test_messages:
        print(f"\nUSER: {msg}")
        handler.handle_chat("player", msg)
        import time
        time.sleep(0.2)  # Let handler respond

    handler.stop()
    print("\n✅ Chat handler test complete!")
