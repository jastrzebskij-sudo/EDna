# Design Principle: Automation Boundary

Established 2026-09-15, in response to researching CAPI's fleet-carrier jump limits and FDev's stated position on unattended automation.

## The rule

**The only things that may affect the in-game universe are the player's own real-time interactions with the game client.** Nothing we build may act on the game world autonomously or unattended — no scheduled jump sequences, no bot-driven navigation, no unattended input injection. This isn't just a ToS-avoidance stance; it's a considered design choice: the assistant's job is to plan, inform, and enrich the player's decisions, not to play the game *for* them.

## Three tests, not one

Two ways a proposed automation can fail the rule above, plus the one way it clearly passes:

1. **One burst, fully player-initiated → fine, however many steps it contains.** The whole packaged sequence fires and completes *within* the player's triggering moment — no pause, no wait. Example: deploying a full swarm of mining limpets is, mechanically, several separate fire-limpet actions a player currently does one at a time in quick succession — packaging that into a single trigger just automates a tight, already-continuous manual loop. Same category as EDCoPilot's route-plotting/targeting macros. The player initiates it and it's over in the time a real player's hands would take, just more precisely.
2. **Waits on the world, then acts again, unattended → not fine.** The sequence has to pause and wait on an external, time-delayed game-state change (a jump completing, a cooldown ending, docking clearance) and then continues **without the player re-triggering it**. Carrier auto-jumping is the anti-pattern here: fire, wait (possibly minutes, off-screen), fire again with no further player involvement — what FDev called "most likely not acceptable," and what CATS/FCAutojumper actually implement.
3. **Substitutes sustained/skill-based control for the player's own → not fine, independent of timing.** Some in-game actions aren't discrete, instantaneous inputs at all — they're continuous piloting or interaction that unfolds over time and is itself the gameplay (flying to a location, working the FSS tuning band, combat maneuvering, docking approach, SRV driving). Automating one of these isn't "packaging a burst" no matter how you frame it — it's software operating the controls in place of the player for a skill-relevant stretch of time. This fails the *top-level* rule directly (only the player's own interaction may affect the universe), even when there's no external wait involved. Test 2 is about *timing*; test 3 is about *whether it was ever a discrete input to begin with*.

So: **package tight, already-continuous bursts of discrete inputs into a single trigger — freely.** Never bridge a *time gap* the player would otherwise have to be present for (test 2), and never hand sustained/skill-based control over to software at all (test 3), regardless of whether anything is waiting on anything.

## What this permits

- **Single-trigger macros covering a known burst of discrete inputs** — deploying a limpet swarm, entering a game mode (FSS, SRV deploy, fuel scoop toggle), a standard docking-request-then-request-slot sequence, a fixed pre-jump checklist (retract hardpoints, raise shields, etc.) — anything a player already does as a tight back-to-back sequence of button presses, packaged into one press.
- **Planning, analysis, and narration** — anything that helps the player decide what to do next (route suggestions, engineering material checklists, market/outfitting analysis via CAPI, narrated system/status context, "this system's already been surveyed, here's the briefing") is unrestricted, since it doesn't touch the game state itself.
- **CAPI reads, and CAPI's limited legitimate writes** (e.g. fleet carrier commodity/service orders) — these are Frontier-sanctioned account actions, not simulated player input, and are fine.

## What this rules out

- Any sequence that pauses to wait on a time-delayed game-state change and then continues **without the player re-triggering it** (test 2) — confirmed by FDev's own stated position: acceptable for in-the-moment actions like a docking request, "most likely not acceptable" for unattended multi-jump carrier automation.
- Background/scheduled bots that watch state and act on their own initiative (e.g. an auto-jumper that fires the next carrier jump when the last one completes, unattended).
- **Any sustained or skill-based control task performed by software instead of the player** (test 3) — flying the ship to a location, running the actual FSS scan/tuning, combat maneuvering, SRV driving, docking approach. These are the gameplay, not a mechanical formality around it, no matter how routine or "loop-like" they feel.
- Anything requiring input-simulation tooling that runs whether or not the player is at the keyboard.

## Precedent already in our toolset

- **EDCoPilot's route-plotting/targeting** — single player action → one bounded keypress sequence. This is the model, not the exception.
- **CATS / FCAutojumper** (researched, not used) — explicitly the anti-pattern: unattended multi-jump automation via simulated keypresses while the player is away. Their own docs concede this is against FDev's ToS. Ruled out.

## Worked example: carrier multi-jump assist (approved pattern)

Multi-jump carrier travel was raised as a test case, and it's a useful worked example of the principle because the obvious version fails the test and a refined version passes it cleanly.

**Ruled out:** the tool plots a multi-hop route and then fires each successive jump itself once the prior jump's cooldown elapses, unattended. This is exactly CATS/FCAutojumper's shape — wait on a time-delayed state change, then act without the player. Also not actually analogous to ship travel, since ships have no unattended multi-jump autopilot either (the player engages the FSD manually for every hop along a plotted route).

**Approved:** the tool does everything *except* fire the jump —
- Plans the multi-hop route (intermediate jump points within the carrier's single-jump range).
- Tees up / targets the next system in sequence.
- Notifies the player when the jump cooldown has concluded and the next hop is ready.
- The player manually triggers every single jump, same as they'd manually engage FSD for every hop of a plotted ship route.

This is the correct shape: everything that changes game state stays a per-instance manual player action; everything else (planning, prep, notification) is unrestricted assistance. It's a materially different thing from the ruled-out version, not a relabeling of it. This is now the reference pattern for evaluating any other "assist this multi-step in-game process" idea — the state-changing step(s) stay manual and per-instance; everything around them can be automated freely.

## Recommendation format: stated action + stated criteria

This is what actually differentiates the assistant from existing data-display tools (EDDiscovery, Elite Observatory, ED Materials Helper, etc.) — those surface raw stats and leave interpretation to the player. This project's job is to go one step further: **synthesize the data into an explicit recommended action, with the reasoning stated alongside it** — not just "here's the data" but "recommended course of action is X, based on Y criteria." The player can disregard or override it freely; the assistant never enforces or auto-executes its own recommendation (that would collapse straight back into the automation-boundary violations above). The value is in doing the synthesis work the player would otherwise do by hand, not in taking the decision away from them.

This applies wherever the assistant makes a call, not just exploration: "recommended: skip this system, no outstanding value" is a claim standing on stated criteria (already surveyed, no flagged bodies), not a bare data dump. Any future recommendation-producing feature should follow the same shape — name the action, name the criteria, leave the trigger to the player.

## Worked example: system-arrival assist (split verdict)

Raised as a candidate, and useful precisely because it doesn't resolve to one verdict — pulling it apart into its actual steps is what surfaced test 3 above.

The sequence as a player experiences it: check whether the system's already known → fly to gain distance from the star → discovery-scan (honk) → scoop fuel if worthwhile → FSS to see what's worth further exploration.

| Step | What it actually is | Verdict |
|---|---|---|
| Check if system already known/briefed | Database lookup, no game-state touch | **Approved** — pure information |
| Discovery scan ("honk") | Single instantaneous button | **Approved** — same category as limpets |
| Enter FSS mode | Single instantaneous button | **Approved** — mode entry only |
| Toggle fuel scoop on | Single instantaneous button | **Approved** — the toggle itself; see below |
| Gain distance from the star | Sustained piloting over time | **Ruled out** — test 3: this is flying, not a discrete input |
| Actually being in scooping range | Depends on the piloting above | **Ruled out** — inherits from piloting |
| Run the FSS scan (tune/detect signals) | Active, skill-based player interaction | **Ruled out** — test 3: this is the gameplay itself |

Net: the assist can tell the player what's already known about the system, fire the honk, flip mode/toggle buttons, and narrate results — but the flying and the actual scanning stay the player's own hands, full stop. This is the general shape to expect from most "gameplay loop" candidates: the button-press bookends are approvable, the piloting/skill interior is not.

## Approved patterns (confirmed)

- **Mining limpet-swarm deployment** — one burst of discrete fire-limpet inputs, packaged into a single trigger.
- **Carrier multi-jump assist** — plan route, tee up next target, notify on cooldown; player fires every jump (see worked example above).
- **System-arrival bookends** — known-system briefing, honk, FSS/scoop mode-entry toggles (see worked example above; the piloting/scanning interior is explicitly NOT included).

## Candidate action-loops worth cataloging later

Likely more across mining (prospector-limpet-then-collector-limpet handoffs), combat loadout switching, and station arrival/departure checklists (docking request sequences, module toggles on approach). Worth keeping a running list as they come up rather than trying to enumerate them all now — flag one whenever it comes up in conversation and it can be added here.

## Implication for future builds

Any "participate in gameplay" feature (MCP-wrapped CAPI tool, a Stream-Deck-style macro launcher, a route/plan advisor) should be designed around **a single explicit trigger firing a bounded burst of action that completes without waiting on the world**, never a standing/time-spanning/autonomous process. If a feature idea can't be described that way, it's out of scope as designed and needs to be reshaped, not just gated behind a confirmation prompt.

# Design Principle: Tedium Is Opt-In

Established 2026-09-15. Independent of the automation boundary above — this one's about UX quality within whatever stays manual, not about what may touch game state. Elite Dangerous has drawn real, longstanding criticism for grind-heavy loops (rank/reputation farming, engineering-material collection, credit-grinding activities repeated dozens or hundreds of times to hit a threshold). This project shouldn't design new features that add to that experience unexamined, or spring it on a player mid-task.

## The rule

**Wherever a feature's design has a choice, prefer the version that requires less repetitive, tightly-looped manual activity. Where repetition is genuinely unavoidable to reach a stated goal, tell the player up front, in concrete terms, how much of it to expect before they commit.** Grinding isn't banned — plenty of it is inherent to the game itself, not something this project controls — but a player should walk into it knowingly, not discover it three iterations in. Tedium is something the player opts into, not something a recommendation quietly assumes.

## What this looks like in practice

- **Prefer low-repetition paths when a recommendation has options.** If two routes to a stated goal exist and one requires materially less repeated grinding than the other, the lower-repetition path is the default recommendation — not automatically the "best" one in every other respect, but the one that should be surfaced first, with the higher-grind alternative offered as a stated option rather than silently equal.
- **State an effort estimate as part of the recommendation's criteria**, per the recommendation-format pattern above ("stated action + stated criteria"). An estimate of repetition count/time belongs in that criteria alongside everything else: not just "recommended: farm Grade 5 engineering material X at site Y" but "...expect roughly N collection passes / about T minutes of that loop, based on typical yield per pass." This is a natural extension of the existing pattern, not a new one — effort is just another criterion the player deserves stated up front, same as jump range or cost.
- **Flag threshold-based grinds explicitly wherever they appear** — reputation/rank requirements for permits or engineer unlocks, material farming for blueprint grades, community-goal contribution thresholds, credit-grinding for a ship/module purchase. Wherever the assistant already produces output that depends on one of these (permit readiness in `ship-build-advisor.md`, engineering material checklists), the output should name the grind and give a realistic scope, not just the requirement itself.
- **Don't understate it to make a recommendation look better.** An accurate "this will take a while" is more useful, and more trustworthy, than a rosy estimate that turns out short — the whole value of this project rests on the player trusting the stated criteria behind a recommendation.

## Worked examples

- **Engineering material farming** (ties into `ship-build-advisor.md`'s new-build/optimization features): recommending a specific engineering blueprint grade should come with a stated material cost and, where the material is scarce/RNG-gated (e.g. a low-yield surface material needing many collection passes), an honest scope of how much farming that implies — not just "you need 5x Proto Radiolic Alloy."
- **Permit/rank grinding** (`ship-build-advisor.md` Feature D): the unlock-requirement text for a system should say what kind of grind is behind a reputation threshold (roughly how much of what activity, if that's knowable) rather than just naming the rank needed.
- **Route/system choice when multiple options satisfy a goal**: if the exploration-triage or ship-build advisor ever has to choose among several routes/sites/targets that are roughly equivalent except for how much repeated activity each implies (e.g. two candidate mining sites, one requiring far more prospecting passes per ton than the other), the lower-repetition option is the one recommended first.

## Relationship to the automation boundary

This principle doesn't loosen the automation boundary above — a tedious loop doesn't become automatable just because it's tedious; test 1/2/3 still apply in full. What this principle changes is *which* manual loop gets recommended and *how honestly its scope gets described* — it's a design-quality rule for the advisory content itself, not a carve-out for automating repetition away.

## Open items

- No stated methodology yet for turning "typical yield per pass" into a reliable pass-count estimate — would need real data (community-sourced drop rates, or the player's own logged collection history) rather than guessing. Worth flagging as a data-source question if/when a feature that needs this gets built.
- Where "lower-repetition" and "objectively better outcome" (e.g. cheaper, faster travel, higher-grade result) conflict, the recommendation should state both options and let the player choose — not silently pick one axis to optimize.
