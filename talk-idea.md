No, I don’t think it’s a waste of time.

I also don’t think the most interesting part of the demo is what you might instinctively lead with.

If you show:

“Look, an LLM plays Diablo.”

People will think:

“Cool bot.”

That’s underselling it.

The more interesting story is:

“Here’s a protocol for embedding AI players into an authoritative game engine.”

Then Diablo becomes the proof.

⸻

If I were watching a 10-minute demo, I’d want to see something like this:

1. Architecture (60 seconds)
    * Headless Devilution clients.
    * GAP adapter.
    * AI agents are actual network players.
2. Embodiment (2 minutes)
    * Airhead joins as Player 2.
    * Beavis joins as Player 3.
    * No privileged API.
    * They use the same mechanics you do.
3. Coordination (3 minutes)
    * “Hold here.”
    * “On me.”
    * Portal usage.
    * Stairs.
    * Loot.
    * Show that the engine remains authoritative.
4. Observability (2 minutes)
    * Live council recommendations.
    * Current intent lease.
    * Decision trace.
    * Explain why they chose an action.
5. Framework (2 minutes)
    * The Diablo adapter is ~X lines.
    * Explain what another engine would need to provide.
    * Show the protocol.

That’s a framework demo.

⸻

What makes it interesting isn’t that Airhead is clever.

It’s that you’ve made the reasoning visible.

Most AI demos look like magic.

Yours can say:

HazardAgent      score 9.2
LootAgent        score 4.1
MovementAgent    score 3.7
Winner:
HazardAgent
Reason:
Standing in fire.

That’s immediately understandable.

⸻

There’s another audience I think would appreciate it:

engine programmers.

A lot of game AI discussions stay inside Unity or Unreal.

You’re working against a small C++ engine that predates modern AI tooling by decades, yet you’ve kept the engine authoritative and pushed the intelligence out into an external runtime.

That’s an interesting architectural choice regardless of Diablo.

⸻

I also think the decision tracing (Track E) strengthens the demo more than almost any gameplay feature.  

When someone asks:

“Why did the rogue do that?”

you won’t have to shrug.

You can literally replay the decision.

That’s unusual.

⸻

One thing I would encourage is to frame the project carefully.

Avoid:

“This is AGI playing Diablo.”

Emphasize something like:

“This is an experiment in building reusable infrastructure for embodied AI teammates in existing game engines.”

That’s a much stronger engineering claim, and it’s one you’ve actually substantiated with the architecture you’ve built.

If, six months from now, someone writes a Godot adapter and most of GAP comes across unchanged, that’s a compelling demonstration that the abstractions were chosen well.

And honestly, I think there are people in both game AI and agent infrastructure who would find that interesting—not because it’s Diablo, but because it explores a clean separation between an authoritative simulation and an external, observable, testable agent runtime.



I actually think your instincts about Hacker News are reasonable.

It’s fantastic for some things, but a project like GAP can easily get flattened into one of two narratives:

* “Why didn’t you just use behavior trees?”
* “LLMs are hype.”

Neither really engages with what you’re building.

I’d look for communities where people care about architecture and experimentation, not just hot takes.

A few that strike me as good fits:

AI Engineers / Agent Builders

People building agent runtimes are much closer to your audience than people building chatbots.

They’ll appreciate questions like:

* Why leases?
* Why an authoritative engine?
* Why trace every decision?
* Why TLA+?

⸻

Game AI Conference (AIIDE)

The Association for the Advancement of Artificial Intelligence runs the AIIDE conference every year.

Historically it’s been full of people working on:

* game AI
* planning
* NPC behavior
* procedural systems

Your project isn’t a conventional research paper, but it’s very much in the same ecosystem.

⸻

Game Developers Conference

Not necessarily the main AI track.

The “AI Summit,” gameplay programming, or postmortem-style talks might actually be a better fit.

A talk titled something like:

Building an External AI Runtime for a 25-Year-Old Game Engine

would catch my attention.

⸻

Engine communities

Ironically, I think engine developers may appreciate this more than AI people.

Godot developers, Bevy developers, and engine programmers are often interested in:

* protocol design
* adapters
* observability
* deterministic simulation

because those are problems they already think about.

⸻

Open source maintainers

Once GAP is public enough, the most valuable audience may simply be other developers who think:

“I wonder if I could make this work with my engine.”

One good adapter from someone else would validate the abstraction far more than a thousand upvotes.

⸻

I would also consider something different

Don’t underestimate the value of a well-produced technical walkthrough.

Not a flashy YouTube video.

More like a conference talk that happens to be on YouTube.

Imagine 20–30 minutes:

* Why Diablo?
* Why headless multiplayer?
* Why the sidecar failed.
* Why embodiment mattered.
* The GAP protocol.
* Intent leases.
* Decision tracing.
* TLA+ boundaries.
* Live demo.

That’s evergreen.

People can discover it years later.

⸻

The audience I think would enjoy it most

Honestly?

The kind of engineer who smiles when they hear:

“We deleted 2,000 lines of hacks because the engine already knew how to do it.”

Those people exist.

They’re usually:

* engine programmers
* distributed systems people
* robotics folks
* simulation engineers
* game AI researchers

They’re less interested in “look what AI can do” and more interested in “look at this architecture.”

⸻

One final thought.

When you eventually present GAP, I’d make the title about architecture, not AI.

Something like:

GAP: A Protocol for Embedding Autonomous Agents into Authoritative Game Engines

or

Building AI Teammates Without Modifying the Simulation

Those titles attract exactly the people who will ask interesting questions.

Because I don’t think the enduring contribution is “AI in Diablo.”

It’s the design pattern:

Keep the simulation authoritative. Put intelligence outside it. Make the interface observable, replayable, and testable.

That’s a conversation I’d happily attend, and I suspect a lot of experienced engineers would too.
I actually think this may be the philosophical core of GAP.

Not “LLMs can play games.”

Not “AI replaces game AI.”

But:

An LLM is another subsystem.

That’s a much more interesting claim.

⸻

Reading through your roadmap, what struck me is how often the solution was not “ask the model.”

Examples from just the last couple of days:

* Hazard detection → engine exposes HZ=. The LLM doesn’t infer fire from prose; the engine reports hazards.
* Spell metadata → engine exports spell definitions. No duplicated prompt tables.
* Item ownership → the host game is authoritative.
* Intent leases → don’t ask the LLM the same question every 600 ms.
* Decision tracing → record deterministic state instead of hoping the model remembers.

The pattern is consistent.

Every time there is an existing deterministic solution…

…you use it.

The LLM gets involved when the question is genuinely one of judgment or language.

⸻

That leads to an architecture I really like:

Physics
    ↓
Engine
Game Rules
    ↓
Engine
Authority
    ↓
Engine
Perception
    ↓
Adapter
Execution
    ↓
Tactics
Coordination
    ↓
Council
Judgment
    ↓
LLM

Each layer is doing the thing it’s naturally good at.

Nobody is pretending the LLM should simulate Diablo.

⸻

This also explains why your roadmap doesn’t read like “replace everything with AI.”

Instead it reads like:

Can the engine already do this?
Yes?
    Use it.
No?
    Can deterministic code do it?
Yes?
    Write an agent.
No?
    Ask the model.

That’s an engineering philosophy.

⸻

Ironically, I think this makes GAP more future-proof.

If next year’s models are twice as capable…

Great.

The architecture doesn’t change.

The council just gets a better advisor.

If somebody wants to replace GPT with a local model…

Great.

Same protocol.

If someone wants zero LLMs…

Most of GAP still exists.

⸻

I think that’s the part that deserves emphasis in any presentation.

There are lots of talks that implicitly say:

“AI changes everything.”

GAP’s message is almost the opposite:

AI changes surprisingly little. It gives you a new capability, but the rest of software engineering still matters.

Protocols still matter.

Adapters still matter.

Observability still matters.

Formal verification still matters.

Deterministic algorithms still matter.

Game engines still matter.

That’s a refreshing perspective, because it treats LLMs as a powerful addition to the toolbox instead of a replacement for every other tool.

Honestly, if I were summarizing GAP in one sentence today, it might be:

GAP is what happens when you build an AI framework like a software engineer instead of like a prompt engineer.

From everything we’ve discussed over the past months, that feels like the through-line. The LLM is important—but it’s one well-defined component in a system whose behavior comes from the interaction of many carefully designed pieces. That’s a much more robust foundation than asking the model to do everything.
