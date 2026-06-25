"""
Base classes for specialist agents
"""

import requests
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from an agent evaluation"""
    command: str       # DSL command: "AT 27", "MV 72 81", "USE 0", etc.
    weight: float      # 0.0-1.0 confidence
    reasoning: str = ""  # Optional debug info


class BaseAgent:
    """Base class for all specialist agents"""

    def __init__(
        self,
        name: str,
        model: str = "qwen2.5:3b",
        ollama_url: str = "http://localhost:11434/api/generate",
        timeout: float = 12.0  # Generous timeout for model warmup during level transitions
    ):
        self.name = name
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = timeout
        self.dormant = False
        self.profile = None  # CharacterProfile (injected by orchestrator)
        self.personality = None  # PersonalityStore (injected by orchestrator)
        # Optional decision-trace sink (ROADMAP Track E). When the orchestrator is
        # tracing it points this at a per-tick list; query_llm then appends every
        # (prompt, response) it produces so the trace can later stub the LLM and
        # reproduce LLM-driven decisions. None (default) = zero overhead.
        self.llm_sink = None
        # Whether to prepend remembered personality context to LLM prompts.
        # Tactical agents (combat/spell) turn this off to stay terse and fast.
        self.use_memory_context = True

    def _memory_preamble(self) -> str:
        """Remembered-personality preamble for prompts, or '' if none/disabled."""
        if not self.use_memory_context or self.personality is None:
            return ""
        try:
            return self.personality.get_behavioral_context(self.name)
        except Exception as e:  # never let memory lookup break a decision
            logger.debug(f"{self.name}: personality context unavailable: {e}")
            return ""

    def set_model(self, model: str):
        """Update model for context-based switching (town vs dungeon)"""
        if self.model != model:
            logger.debug(f"{self.name}: Switching model {self.model} → {model}")
            self.model = model

    def evaluate(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Evaluate game state and return weighted recommendation.

        Args:
            state: Game state dictionary

        Returns:
            AgentResponse or None if agent is dormant/no recommendation
        """
        if self.dormant:
            return None

        if not self.should_activate(state):
            return None

        return self._evaluate_impl(state)

    def should_activate(self, state: Dict[str, Any]) -> bool:
        """
        Check if agent should activate based on state.
        Override in subclasses for dormancy logic.
        """
        return True

    def _evaluate_impl(self, state: Dict[str, Any]) -> Optional[AgentResponse]:
        """
        Actual evaluation logic. Override in subclasses.
        """
        raise NotImplementedError

    def query_llm(self, prompt: str, grammar: Optional[str] = None) -> str:
        """
        Query Ollama LLM with optional grammar constraints.

        Args:
            prompt: The full prompt to send
            grammar: Optional GBNF grammar to constrain output

        Returns:
            LLM response text (stripped)
        """
        try:
            # Prepend remembered personality so stored experience shapes the
            # decision (no-op for tactical agents / when nothing is remembered).
            preamble = self._memory_preamble()
            full_prompt = f"{preamble}\n\n{prompt}" if preamble else prompt

            request_payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "num_ctx": 768 if preamble else 512,
                    "temperature": 0.2,
                    "top_p": 0.8,
                    "repeat_penalty": 1.1,
                    "num_predict": 20,  # Keep it very short
                }
            }

            if grammar:
                request_payload["grammar"] = grammar

            resp = requests.post(
                self.ollama_url,
                json=request_payload,
                timeout=self.timeout
            )
            resp.raise_for_status()

            response_text = resp.json()["response"].strip()
            logger.debug(f"{self.name}: LLM response: {response_text[:100]}")

            self._trace_llm(full_prompt, response_text)
            return response_text

        except requests.exceptions.Timeout:
            logger.warning(f"{self.name}: LLM query timed out")
            self._trace_llm(locals().get("full_prompt", prompt), "")
            return ""
        except Exception as e:
            logger.error(f"{self.name}: LLM query failed: {e}")
            self._trace_llm(locals().get("full_prompt", prompt), "")
            return ""

    def _trace_llm(self, prompt: str, response: str) -> None:
        """Record this LLM call into the active decision-trace sink, if any.
        Failures (timeouts) are recorded with an empty response so the trace
        reflects what the council actually saw this tick."""
        if self.llm_sink is not None:
            self.llm_sink.append(
                {"agent": self.name, "prompt": prompt, "response": response}
            )

    def parse_weighted_response(self, response: str) -> Optional[AgentResponse]:
        """
        Parse LLM response in format: "COMMAND weight"
        Example: "AT 27 0.85" or "MV 72 81 0.70"

        Returns:
            AgentResponse or None if parsing fails
        """
        if not response:
            return None

        parts = response.split()
        if len(parts) < 2:
            return None

        try:
            # Check if last part is a weight (0.0-1.0)
            weight = float(parts[-1])
            if not (0.0 <= weight <= 1.0):
                # Not a weight, try to extract command without weight
                command = response
                weight = 0.5  # Default weight
            else:
                # Last part is weight, rest is command
                command = " ".join(parts[:-1])

            return AgentResponse(
                command=command,
                weight=weight,
                reasoning=f"{self.name} evaluated"
            )

        except ValueError:
            # No weight found, use entire response as command
            return AgentResponse(
                command=response,
                weight=0.5,
                reasoning=f"{self.name} evaluated (no weight)"
            )
