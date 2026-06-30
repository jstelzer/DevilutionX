Devilution is already driven quite a bit by claude code running in...... emacs. ❯ ls ~/.emacs.d/straight/repos/claude-code-ide.el

So, it would stand to reason, I'd use something like https://github.com/xenodium/ytr  to compose a HUD for the AI agents. I'd be a pretty slick part ofthe demo IMO 


Oh absolutely. That’s not just slick — that’s demo-grade theater with real utility.

A ytr-style Emacs HUD could show:

* agent state: goal, last action, confidence
* party state: health, mana, threat, current target
* world facts: fire tiles, doors, monsters, loot
* LLM plumbing: model, tokens, latency, prompt size
* decision trace: “why Beavis cast Fireball”
* safety/debug: “standing in fire tolerance exceeded”

The killer demo move is that it’s not a fake overlay. It’s the actual dev cockpit: Devilution running, Claude Code in Emacs, agent telemetry streaming into Emacs frames/widgets, Magit/tests/logs one key away.

That lands because it shows the whole thesis:

The AI player isn’t magic smoke. It’s an observable subsystem.

And visually, it reinforces your point that GAP doesn’t replace the old machinery. It sits beside engine logic, tests, telemetry, and handcrafted rules.

Honestly, a HUD pane like:

Agent: Beavis
Intent: clear_room
Plan: kite fallen, avoid fire, cast when clustered
Risk: medium
Last decision:
  cast_fireball(target=fallen_pack)
Because:
  4 enemies clustered
  ally distance safe
  fire spread east acceptable

…while Diablo is visibly running?

Yeah. That’s the kind of thing people remember.


