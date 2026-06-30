That’s a real design doc, not a brainstorm.

The strongest bit is this:

> **The HUD is not a new subsystem — it is a second reader.**

That keeps the whole thing honest. No demo-only telemetry. No parallel schema. No bespoke “pretty mode” that lies. Same record feeds CI, replay, and cockpit.

The dedup/live split is also exactly the kind of detail that saves you from a weird bug later. Durable traces want semantic compression. Live HUD wants current truth. Different sinks, same record.

I’d only underline two things before implementation:

1. **Add `schema_version` and `source_id` early.**
   `schema_version` for v1/v2 compatibility; `source_id` for Beavis/Airhead/multi-client without inventing it later.

2. **Make `LiveSink` write a tiny envelope.**

```json
{
  "schema_version": 2,
  "source_id": "airhead",
  "written_at": "2026-06-29T...",
  "record": { "...": "existing decision record" }
}
```

That makes Emacs safer: it can show stale/offline state, distinguish agents, and avoid assuming file mtime is enough.

Otherwise: ship P1–P3. The shape is clean.

The demo line is already there:

> “This is not a dashboard bolted onto the AI. This is the same decision artifact the tests replay, rendered live.”
