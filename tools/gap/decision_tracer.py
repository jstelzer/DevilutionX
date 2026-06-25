"""
DecisionTracer — the council's flight recorder (ROADMAP Track E).

Records one JSONL object per `decide()` at the selection point. The trace is a
behavioral oracle: it makes B5 measurable, moves weight tuning offline, turns
regressions into CI failures, and gives any future rewrite a pin to reproduce.

Principle (from the ROADMAP): the *engine* owns outcomes, the *council* owns
decisions. This file records decisions only — it deliberately says nothing about
whether a decision worked in the world. Keep that boundary clean.

Design notes (build it like infra, not a debug print):
- **Versioned schema.** Every record carries ``schema_version``; bump it when the
  shape changes so a v1 corpus is still recognizable to a future replayer.
- **Log on change, not every tick.** While walking to Griswold the council
  re-decides the *identical* arbitration ~2-3×/sec. We hold the last record and
  only flush it when the decision meaningfully changes, carrying a ``repeats``
  count of how many identical re-decisions it stood in for. That count is not
  noise — it's the churn metric B5 Phase 0 is trying to kill, measured for free.
- **Crash-safe-ish.** The held record is flushed on close()/shutdown. A hard
  kill loses at most the single in-flight decision.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class DecisionTracer:
    """Append-only JSONL writer for council decisions, with change-dedup."""

    def __init__(self, path: str):
        self.path = path
        # Line-buffered text append: records land on disk as soon as a line is
        # written, so an interactive `tail -f` shows decisions live.
        self._fh = open(path, "a", buffering=1, encoding="utf-8")
        # The most recent record, held back so we can fold identical follow-ups
        # into its `repeats` count before flushing it to disk.
        self._held: Optional[Dict[str, Any]] = None
        self._held_sig: Optional[str] = None
        self.written = 0       # records flushed to disk
        self.suppressed = 0    # identical re-decisions folded into a `repeats`
        logger.info(f"📼 Decision trace → {path} (schema v{SCHEMA_VERSION})")

    @staticmethod
    def _signature(record: Dict[str, Any]) -> str:
        """A decision is 'the same' when the contenders, their scores (rounded to
        absorb float jitter), the winner, the command, and the locale match. The
        tick and exact monster HP deliberately do NOT count — re-deciding an
        unchanged arbitration is precisely the churn we want to collapse."""
        recs = sorted(
            (r["agent"], round(r["score"], 1)) for r in record["recommendations"]
        )
        sig = (
            record["in_town"],
            record["floor"],
            record["winner"],
            record["command"],
            tuple(recs),
        )
        return json.dumps(sig, default=str)

    def record(
        self,
        *,
        tick: int,
        floor: int,
        in_town: bool,
        dsl: str,
        recommendations: List[Tuple[str, Any, float]],
        commitment: Dict[str, Any],
        tactical_mode: str,
        llm: List[Dict[str, str]],
        winner: str,
        command: str,
    ) -> None:
        """Build a record from the selection-point data and queue it for write.

        ``recommendations`` is the orchestrator's final ``(name, AgentResponse,
        score)`` list as it enters ``max()`` — i.e. post tactical-mode and
        post-commitment, exactly what arbitration saw. We capture ``weight`` and
        ``score`` (priority is folded into ``score`` upstream and isn't separable
        here; ``score`` is what arbitration actually compares, so the
        deterministic replay test needs nothing more).
        """
        try:
            rec = {
                "schema_version": SCHEMA_VERSION,
                "tick": tick,
                "floor": floor,
                "in_town": in_town,
                "dsl": dsl,
                "recommendations": [
                    {
                        "agent": name,
                        "weight": round(response.weight, 4),
                        "score": round(score, 4),
                        "reasoning": response.reasoning,
                    }
                    for (name, response, score) in recommendations
                ],
                "commitment": commitment,
                "tactical_mode": tactical_mode,
                # Only the LLM agents that actually fired this tick (combat/chat/
                # shopping/griswold/adria + base). Baked in from day one so the
                # corpus can stub query_llm and reproduce LLM-driven decisions.
                "llm": llm,
                "winner": winner,
                "command": command,
                "repeats": 0,
            }
            self._offer(rec)
        except Exception as e:  # a trace must never break a decision
            logger.warning(f"DecisionTracer.record failed: {e}")

    def _offer(self, rec: Dict[str, Any]) -> None:
        sig = self._signature(rec)
        if self._held is not None and sig == self._held_sig:
            # Identical re-decision: fold into the held record's repeat count.
            self._held["repeats"] += 1
            self.suppressed += 1
            return
        # Decision changed (or first record): flush whatever we were holding,
        # then hold the new one so its own repeats can accumulate.
        self._flush_held()
        self._held = rec
        self._held_sig = sig

    def _flush_held(self) -> None:
        if self._held is None:
            return
        self._fh.write(json.dumps(self._held, default=str) + "\n")
        self.written += 1
        self._held = None
        self._held_sig = None

    def close(self) -> None:
        """Flush the in-flight record and close the file. Safe to call twice."""
        if self._fh is None:
            return
        try:
            self._flush_held()
            self._fh.flush()
            self._fh.close()
            total = self.written + self.suppressed
            ratio = (self.suppressed / total) if total else 0.0
            logger.info(
                f"📼 Decision trace closed: {self.written} records written, "
                f"{self.suppressed} identical re-decisions folded "
                f"({ratio:.0%} churn)."
            )
        except Exception as e:
            logger.warning(f"DecisionTracer.close failed: {e}")
        finally:
            self._fh = None


# --------------------------------------------------------------------------- #
# Self-test: `python decision_tracer.py` (also run by dev.sh test).
# --------------------------------------------------------------------------- #
def _selftest() -> None:
    import os
    import tempfile
    from dataclasses import dataclass

    @dataclass
    class _Resp:
        weight: float
        reasoning: str = ""

    tmp = tempfile.mkdtemp(prefix="gap_trace_")
    path = os.path.join(tmp, "trace.jsonl")
    tr = DecisionTracer(path)

    def rec(tick, winner, command, recs, *, in_town=True, floor=0):
        tr.record(
            tick=tick, floor=floor, in_town=in_town, dsl=f"T={tick} F={floor}",
            recommendations=recs, commitment={"incumbent": winner, "streak": 0},
            tactical_mode="follow",
            llm=[{"agent": "Griswold", "prompt": "sell?", "response": f"{command} 0.7"}],
            winner=winner, command=command,
        )

    griswold = [("Griswold", _Resp(0.7, "sell junk"), 4.2), ("Movement", _Resp(0.3, "follow"), 0.9)]
    # 1 distinct decision, repeated 3× (tick advances, scores jitter within rounding).
    rec(1, "Griswold", "IN 5", griswold)
    rec(2, "Griswold", "IN 5", [("Griswold", _Resp(0.7, "sell junk"), 4.23), ("Movement", _Resp(0.3, "follow"), 0.88)])
    rec(3, "Griswold", "IN 5", griswold)
    # Decision changes → flushes the held Griswold record (repeats=2), holds this.
    rec(4, "Combat", "AT 12", [("Combat", _Resp(0.9, "attack"), 7.2)], in_town=False, floor=2)
    tr.close()

    with open(path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    assert len(lines) == 2, f"expected 2 written records, got {len(lines)}"
    assert lines[0]["winner"] == "Griswold" and lines[0]["repeats"] == 2, lines[0]
    assert lines[0]["schema_version"] == SCHEMA_VERSION
    assert lines[0]["recommendations"][0]["agent"] == "Griswold"
    assert lines[0]["llm"][0]["agent"] == "Griswold"
    assert lines[1]["winner"] == "Combat" and lines[1]["repeats"] == 0, lines[1]
    assert tr.suppressed == 2 and tr.written == 2
    print(f"✅ decision_tracer self-test passed ({path})")

    os.remove(path)
    os.rmdir(tmp)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _selftest()
