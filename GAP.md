
# GAP: Game Agent Protocol (v0.1 Draft)

**A lightweight, open protocol for real-time AI co-op and automation in games.**  
**License:** Spec under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/); reference implementations under [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0).

---

## 1. Goals & Philosophy

GAP exists to let **AI agents** (local or remote) act as co-op partners, testers, or automated controllers for games with minimal friction.  

- **Engine-agnostic:** Works for ARPGs like Diablo, FPS like Doom, RPGs like Baldur's Gate.  
- **Real-time & low-latency:** Targets human-like reaction times (~150–200 ms).  
- **Safe & open:** Free to use, simple to embed, permissively licensed, no patents.  
- **Deterministic:** Commands integrate with game logic directly, not via OS input hacks.  
- **Extensible:** Can grow to support replay, multi-agent, or learning scenarios.

---

## 2. High-Level Architecture


```
Client               Server
  |    hello --------> |
  | <------- hello     |
  | <== state@30Hz ==  |
  | intent(use_pot) -->|
  | <----- ack         |
  | <== state@30Hz ==  |

```

- **State**: Game publishes world/player info at fixed cadence (~30–40 Hz).  
- **Intents**: Agent sends high-level actions (move, cast, pickup, etc.).  
- **Transport**: Duplex WebSocket with JSON messages (MVP).  

---

## 3. Core Concepts

### 3.1 Tick & Pacing
- Game simulation ticks at its native rate (60–144 Hz etc.).  
- GAP decouples via:
  - **State cadence:** Publish every 25–33 ms (~30–40 Hz).  
  - **Intent caps:** ≤10 intents/sec, ≤5 applied per tick.  
  - **Coalescing:** Drop redundant move/aim commands in the same tick.  

### 3.2 Headless Mode
- `--headless` flag disables rendering/UI but keeps sim, netcode, and GAP active.  
- Ideal for AI seats or CI testing.

### 3.3 Deterministic Input
- Intents applied at the start of each tick before sim update.  
- Uses existing engine APIs (`MovePlayerTo`, `CastSpell`, etc.), **not OS input events**.

---

## 4. Transport: WebSocket Layer

### 4.1 Connection
- **Default:** `ws://127.0.0.1:7777/gap`  
- **Subprotocol:** `gap.v0`  
- **Auth:** Optional bearer token in handshake or first `auth` message.  

### 4.2 Message Envelope

```json
{
  "type": "state" | "intent" | "ack" | "error" | "hello" | "ping" | "pong",
  "seq": 12345,          // for intents + acks
  "tick": 45123,         // sim tick from server
  "ts": 1735432456,      // unix ms timestamp
  "data": { ... }        // payload
}
```
5. Message Types
5.1 hello

Capabilities + versioning. Sent by both sides on connect.
```
{
  "type":"hello",
  "data":{
    "gap":"0.1.0",
    "game":"DevilutionX",
    "features":["headless","chatbridge"],
    "rateLimits":{"intentsPerSec":10,"maxPerTick":5}
  }
}
```

5.2 state (Server → Client, ~30–40 Hz)

Minimal ARPG example:

```
{
  "type":"state",
  "tick": 45123,
  "data": {
    "player": {
      "id":0,"hp":72,"hpMax":100,"mana":40,"manaMax":90,
      "pos":[123,87]
    },
    "actors":[{"id":42,"kind":"Skeleton","hp":38,"pos":[127,89]}],
    "items":[{"id":9001,"name":"Short Sword","pos":[120,92]}],
    "cooldowns":{"spell1":0,"heal":320},
    "map":{"w":160,"h":112}
  }
}
```

5.3 intent (Client → Server, rate-limited)
```
{
  "type":"intent",
  "seq": 1029,
  "data": {
    "cmd": "move_to",      // move_to | cast | use_potion | pickup | say | stop
    "x":130,"y":88,        // per-command args
    "slot":1,
    "id":9001,
    "text":"Portal NW",
    "targetTick":45125     // optional scheduling
  }
}

```

5.4 ack / error

Server confirms or rejects intents.

```
{ "type":"ack", "seq":1029, "tick":45123 }
{ "type":"error", "seq":1030, "err":"rate_limited" }

```

5.5 Heartbeats

ping every 5s; reply with pong.

Drop connection on ≥15s silence.

6. Reference Implementation Plan
6.1 Server (Game Side)

Enable via: --gap-ws=127.0.0.1:7777

Core modules:

gap_ws.*: WebSocket server, JSON encoding, rate limits

gap_intent.*: Intent structs + coalescing

gap_state.*: State structs + collectors

gap_input_mux.*: Merge SDL + IPC inputs

Hook points:

Start of tick: Drain intents (≤5/tick), apply via existing engine calls.

After sim update: Publish state if pacer triggers.

6.2 Client (Agent Side)

Any language w/ WebSocket + JSON works.

Python pilot:

Reads state at 30 Hz

Sends intent (potion if hp<25%, kite away from enemies)

Optional: in-game say() for co-op chatter

7. Security & Safety

Auth: Optional bearer token.

Local-only by default; wss:// + TLS for remote.

Panic key: In-game hotkey disables all intent processing.

Rate limits: Hard-coded + advertised in hello.

Drop on overload: Never block game loop; skip frames if send buffer congested.

8. Future Extensions

Replay logs: (tick,state,intent) for debugging/training.

Multi-agent: Multiple clients controlling different players.

Voice hooks: TTS for in-game callouts.

Native bindings: C, C++, Python, Rust SDKs.

Non-ARPG schemas: FPS (aim, fire), RTS (select, build).

9. Example Timing Diagram

```
Client               Server
  |    hello --------> |
  | <------- hello     |
  | <== state@30Hz ==  |
  | intent(use_pot) -->|
  | <----- ack         |
  | <== state@30Hz ==  |
```

10. Licensing & Governance

Code: Apache-2.0 (patent grants, commercial-safe).

Spec/docs: CC-BY-4.0 (attribution, remixable).

Contributions: GitHub PRs; lightweight steering group if adoption grows.

11. Minimal v0.1 Checklist

 WebSocket duplex channel (JSON)

 state, intent, ack, error, hello, ping/pong messages

 Pacing: 30–40 Hz state, ≤10 intents/sec, ≤5/tick applied

 Headless mode flag

 Rate limits + panic key

 Python pilot client

 DevilutionX adapter (move, cast, potion, chat)

This is a living document. v0.1 aims for a working Diablo/DevilutionX demo; future versions will generalize schemas and add features.
```
---

This keeps the **vision big**, the **MVP scope tight**, and avoids burying us in micro-optimizations too early.  

If you want, I can scaffold a **`gap-spec/` GitHub repo** with this Markdown, license files, and a skeleton reference implementation so you can start tracking issues and PRs. Do you want me to prep that next?

```
