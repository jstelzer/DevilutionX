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
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# v2 (2026-06-29): records gained `source_id` (which toon/client produced the
# decision) and each `llm[]` entry may carry `model`/`prompt_tokens`/`out_tokens`/
# `latency_ms`. v1 corpora still parse — the new keys are additive and optional.
SCHEMA_VERSION = 2


def build_decision_record(
    *,
    tick: int,
    floor: int,
    in_town: bool,
    dsl: str,
    recommendations: List[Tuple[str, Any, float]],
    commitment: Dict[str, Any],
    tactical_mode: str,
    llm: List[Dict[str, Any]],
    winner: str,
    command: str,
    source_id: str = "?",
) -> Dict[str, Any]:
    """Build the canonical decision record from selection-point data.

    Factored out of any single sink so every telemetry sink (durable
    `DecisionTracer`, live `LiveSink`, any future remote sink) renders the *same*
    object — there is no "pretty mode" that can drift from what CI/replay see.

    ``recommendations`` is the orchestrator's final ``(name, AgentResponse,
    score)`` list as it enters ``max()`` — post tactical-mode, post-commitment,
    exactly what arbitration compared.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "source_id": source_id,
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
        # Only the LLM agents that actually fired this tick (combat/chat/shopping/
        # griswold/adria + base). Each entry: {agent, prompt, response} plus, when
        # captured, {model, prompt_tokens, out_tokens, latency_ms} (schema v2).
        "llm": llm,
        "winner": winner,
        "command": command,
        "repeats": 0,
    }


class DecisionTracer:
    """Append-only JSONL writer for council decisions, with change-dedup."""

    def __init__(self, path: str, source_id: str = "?"):
        self.path = path
        self.source_id = source_id
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
            record.get("source_id", "?"),
            record["in_town"],
            record["floor"],
            record["winner"],
            record["command"],
            tuple(recs),
        )
        return json.dumps(sig, default=str)

    def record(self, **kwargs: Any) -> None:
        """Convenience: build a record from selection-point kwargs and queue it.

        The orchestrator builds the record once (via ``build_decision_record``) and
        fans it out to every sink with :meth:`offer`; this wrapper exists so the
        self-test — and any single-sink caller — can keep passing raw kwargs.
        ``source_id`` defaults to this tracer's own id when omitted.
        """
        try:
            kwargs.setdefault("source_id", self.source_id)
            self.offer(build_decision_record(**kwargs))
        except Exception as e:  # a trace must never break a decision
            logger.warning(f"DecisionTracer.record failed: {e}")

    def offer(self, rec: Dict[str, Any]) -> None:
        """Accept a pre-built record: fold it into the held one if the decision is
        identical (bumping ``repeats``), else flush the held record and hold this.
        Safe to call from the orchestrator's sink fan-out."""
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


class LiveSink:
    """Live cockpit feed: writes the *current* decision to a single JSON file.

    The opposite of :class:`DecisionTracer` by design. The tracer compresses —
    it holds a record and folds identical re-decisions to measure churn, so it
    lags the present by one decision. The HUD wants *current truth* every tick.
    So this sink does no dedup: it overwrites ``path`` with the latest record on
    every :meth:`offer`, and Emacs polls that one tiny file.

    The record is wrapped in a small envelope so the reader can attribute and
    age the feed without trusting file mtime: ``source_id`` says which toon,
    ``written_at`` lets the HUD show "stale" past a threshold, and
    :meth:`close` flips ``offline`` so a clean shutdown reads as OFFLINE rather
    than a frozen-but-maybe-live panel. Writes are atomic (temp + ``os.replace``)
    so a polling reader never sees a half-written file.
    """

    def __init__(self, path: str, source_id: str = "?"):
        self.path = path
        self.source_id = source_id
        self._last: Optional[Dict[str, Any]] = None
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        logger.info(f"🖥️  Live HUD feed → {path} (source: {source_id})")

    def _write(self, record: Optional[Dict[str, Any]], *, offline: bool) -> None:
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "source_id": self.source_id,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "offline": offline,
            "record": record,
        }
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(envelope, f, default=str)
        os.replace(tmp, self.path)  # atomic on POSIX: readers see old or new, never partial

    def offer(self, rec: Dict[str, Any]) -> None:
        """Overwrite the live file with this record (no dedup)."""
        try:
            self._last = rec
            self._write(rec, offline=False)
        except Exception as e:  # the HUD feed must never break a decision
            logger.warning(f"LiveSink.offer failed: {e}")

    def close(self) -> None:
        """Stamp the feed OFFLINE (keeping the last record) so the HUD stops
        treating a frozen panel as live. Safe to call twice."""
        try:
            self._write(self._last, offline=True)
            logger.info(f"🖥️  Live HUD feed closed (offline): {self.path}")
        except Exception as e:
            logger.warning(f"LiveSink.close failed: {e}")


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
    tr = DecisionTracer(path, source_id="airhead")
    live_path = os.path.join(tmp, "live.json")
    live = LiveSink(live_path, source_id="airhead")

    def rec(tick, winner, command, recs, *, in_town=True, floor=0):
        # Build once, fan out to both sinks — mirrors the orchestrator.
        record = build_decision_record(
            tick=tick, floor=floor, in_town=in_town, dsl=f"T={tick} F={floor}",
            recommendations=recs, commitment={"incumbent": winner, "streak": 0},
            tactical_mode="follow",
            llm=[{"agent": "Griswold", "prompt": "sell?", "response": f"{command} 0.7"}],
            winner=winner, command=command, source_id="airhead",
        )
        tr.offer(record)
        live.offer(record)

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
    assert lines[0]["source_id"] == "airhead", lines[0]
    assert tr.suppressed == 2 and tr.written == 2

    # LiveSink: file holds the LATEST record (no dedup), wrapped in an envelope;
    # close() flips it offline while retaining that last record.
    with open(live_path, encoding="utf-8") as f:
        env = json.load(f)
    assert env["source_id"] == "airhead" and env["schema_version"] == SCHEMA_VERSION, env
    assert env["offline"] is False and "written_at" in env, env
    assert env["record"]["winner"] == "Combat", env  # last offered, not deduped
    live.close()
    with open(live_path, encoding="utf-8") as f:
        env = json.load(f)
    assert env["offline"] is True and env["record"]["winner"] == "Combat", env
    print(f"✅ decision_tracer self-test passed ({path})")

    os.remove(path)
    os.remove(live_path)
    os.rmdir(tmp)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _selftest()
