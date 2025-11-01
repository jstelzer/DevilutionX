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
        "Ready to fight!",
    ],

    # Status questions
    r"how are you|you ok|you good": [
        "All good!",
        "Ready to go!",
        "Let's do this!",
        "I'm with you!",
    ],

    # Combat requests
    r"attack|fight|kill|engage": [
        "On it!",
        "Attacking!",
        "Got it!",
        "Let's go!",
    ],

    # Movement requests
    r"follow|come|move|here": [
        "Coming!",
        "On my way!",
        "Following!",
        "Right behind you!",
    ],

    # Affirmatives
    r"thanks|thank you|good|nice|great": [
        "Sure thing!",
        "No problem!",
        "You bet!",
        "Anytime!",
    ],

    # Questions about readiness
    r"ready|prepared|set": [
        "Ready!",
        "Let's go!",
        "All set!",
        "Born ready!",
    ],

    # Fallback friendly responses
    r".*": [  # Catch-all
        "Got it!",
        "Okay!",
        "Sure!",
        "Understood!",
    ],
}


class ChatHandler:
    """
    Async chat response handler.

    Runs in separate thread, responds instantly with templates.
    Optionally uses cheap LLM for complex messages.
    """

    def __init__(self, send_message_callback, use_llm: bool = False, model: str = "qwen2.5:0.5b"):
        self.send_message = send_message_callback
        self.use_llm = use_llm
        self.model = model

        self.chat_queue = queue.Queue()
        self.running = False
        self.thread = None

        logger.info(f"ChatHandler initialized (LLM: {use_llm})")

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
        """Use cheap LLM for natural response (optional)"""
        try:
            import requests

            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"You're a terse Diablo companion. Reply in 3 words max to: '{message}'",
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 10,
                    }
                },
                timeout=2.0
            )

            if resp.ok:
                return resp.json()["response"].strip()

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
