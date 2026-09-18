# Engineering Practice: Package Proven Capabilities as Skills

A build-process note, distinct from `design-principles.md` (which governs what's allowed to touch the game) — this one's about how *we* work once something's been figured out.

## The principle

Once a capability's approach has been worked out and proven to actually perform well — the right data source, the right computation, the right recommendation shape — **package it as a reusable skill/tool rather than re-deriving the approach from scratch each time it's needed.** Re-discovering "how do we compute this" or "where does this data come from" repeatedly costs both processing time and tokens, and re-deriving via language-model reasoning each time is also less reliable than calling a fixed, tested implementation once it exists (see the `ship-build-advisor.md` discussion of why the Coriolis stat math should be ported to a deterministic module rather than re-reasoned per request — same logic applies more broadly).

## Where this applies

Watch for any capability that:
- Requires the same multi-step lookup/computation pattern across multiple sessions or requests, or
- Has a data source and processing approach that's been validated and isn't likely to change often, or
- Is expensive enough (in tokens, tool calls, or latency) that re-deriving it each time is wasteful compared to a fixed implementation.

That's the signal to stop treating it as ad hoc reasoning and start treating it as infrastructure: a packaged skill, a standalone module, or a tool the assistant calls directly rather than working out fresh.

## Status

Not there yet on anything in this project — everything so far (exploration triage, surface navigation, ship-build advisor) is still design-phase spec work, not a working, validated capability. This is a forward-looking practice to apply once a capability is built and shown to work well, not before. The first concrete candidate, when it gets there: the ship-stat calculation core (ported from Coriolis, see `ship-build-advisor.md`) — once verified against known outputs, that's exactly the kind of thing that should become a fixed tool rather than something re-reasoned per recommendation.
