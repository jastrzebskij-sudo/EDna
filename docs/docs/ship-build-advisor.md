# Ship Build Advisor

A recommendation-format capability (see `design-principles.md`) covering four related features: new-build recommendations, existing-build evaluation/optimization, a sourcing "shopping list," and permit-readiness checks. All four are informational/advisory only — nothing here purchases, engineers, or travels on the player's behalf; every output is a stated recommendation plus its criteria, executed by the player's own hands. See `design-principles.md`'s recommendation-format section for the pattern this follows.

## Data sources

- **Ship/module/blueprint stats and engineering modifier data**: `EDCD/coriolis-data` (GitHub, JSON, actively maintained — see `tools-reference.md` research). Confirmed to contain real numeric per-grade modifier ranges, required components, and applicable modules (e.g., `Engine_Dirty` grade 2: `optmul: [0.12, 0.19]`, `thermload: [0.3, 0.3]`). This is the same dataset Coriolis's own site runs on — reuse it directly rather than rebuilding it.
- **Engineering combination/stacking math**: confirmed to live in `EDCD/coriolis`'s own source (MIT-licensed, code freely reusable — data remains Frontier's, same status as `coriolis-data`), not its data repo. Specifically `src/app/shipyard/Calculations.js` (`jumpRange`, `shieldStrength`/`shieldMetrics`, `armourMetrics`, `sustainedDps` with per-weapon range falloff/resistances/hardness, `offenceMetrics`/`defenceMetrics`, and — the key piece — `diminishingReturnsShields`, `diminishingReturnsArmour`, `mapIntoDiminishingRange` for stacking multiple effects) and `src/app/shipyard/Ship.js` (the application layer: `setModification()`, `setModuleBlueprint()`, `setModuleSpecial()`, and the `recalculate*`/`update*` chain that fires after any change). This was the main open risk in this doc and it's resolved: reimplement or call into these directly rather than reverse-engineering or approximating the stacking rules.

**Implementation note**: the source being human/AI-readable isn't actually the deciding factor here — the code needs porting regardless, for architectural reasons. Ship-stat math (especially the diminishing-returns stacking) should run as a deterministic, tested function that any recommendation feature calls and gets an exact number back from, not something re-derived via LLM reasoning each time (multi-step floating-point stacking math is exactly the kind of thing that can drift when reasoned through in language rather than executed as code). The concrete next technical step, when this gets built: port just the pure calculation core (`Calculations.js`'s formulas, plus the relevant `recalculate*`/`update*` orchestration from `Ship.js`) into a small standalone Python module, decoupled from Coriolis's React/Redux app shell and build-string-encoding concerns which we don't need — verified against known Coriolis outputs for a handful of test builds before trusting it for recommendations.
- **Current ship loadout**: journal `Loadout` event (full module list including applied engineering blueprints/experimental effects) — this is how "evaluate my existing build" gets its input. Note Inara's own import FAQ confirms a real limitation worth inheriting as a caveat: loadout data is only current for whichever ship you're actively flying; switching ships is needed to refresh each one's data.
- **Credits balance**: CAPI commander profile, or journal `Loadout`/`Cargo`/`Status` events.
- **Module sourcing (shopping list)**: **resolved, and the original assumption was wrong** — see `inara-api-notes.md` for the full research pass. Inara's public developer API has no read-only market/outfitting/commodity endpoints at all; the "Nearest outfitting" web tool (with its discount filter) is backed by Inara's internal database, not exposed programmatically. Artie's own stated guidance to developers is to use **EDDN** (or static dumps) for real-time pricing/availability instead — which is read-access, needs no whitelisting conversation, and is already covered in `tools-reference.md`. Build the shopping list against EDDN's market/outfitting schemas, not Inara.
- **Permits held**: **resolved — dead end, not just unresearched.** Inara's own API docs state the permit system "is not implemented on Inara yet." CAPI's documented profile schema doesn't expose it either (per earlier `tools-reference.md`/`fd-api` research). No known programmatic source currently exists. Feature D below is scoped down accordingly.

## Feature A: New-build recommendation

Given a stated purpose (combat, exploration, mining, trading, multi-crew, etc.) or an explicit "sweet spot" to balance (e.g., maximize jump range while keeping shields above some threshold), compute a recommended ship + module + engineering-grade loadout using the coriolis-data model.

**Output shape**: full loadout recommendation, stated with the criteria behind each notable choice ("recommended: Dirty Drive Tuning grade 2 on thrusters, based on prioritizing speed over heat efficiency per your stated goal") — not just a parts list, the reasoning travels with it, per the project's recommendation-format standard.

## Feature B: Existing-build evaluation / optimization

Read the player's actual current loadout (journal `Loadout` event), compute its current stats via the same model, and recommend specific deltas — swap this module, re-engineer that one to a different experimental effect — to move toward a stated goal or better "sweet spot" balance across competing stats (e.g., jump range vs. speed vs. armor vs. heat).

**Output shape**: current stats stated alongside the recommended changes and why each one helps ("recommended: switch power distributor experimental from Superconducting to Stripped Down, based on your engine-pips-heavy playstyle reducing systems-pip need").

## Feature C: Shopping list

For any recommendation from A or B, produce a sourcing list: which modules are needed, where to buy them (nearest / cheapest, via EDDN's outfitting/commodity data — not Inara, see Data sources above), per-item and total cost, and which required engineering materials the player is missing versus already holds (materials inventory from journal `Materials`/`MaterialCollected`/`EngineerCraft` events). Note: discount-station awareness (Inara's web-only feature) isn't reproducible this way — EDDN gives prices as reported, not a curated "is this discounted" flag. Worth deciding at build time whether that's worth approximating (e.g., flag a price as notably below the galactic average) or just dropping.

**Output shape**: a stated shopping list with source and cost per item, total cost, and a materials checklist — purely informational. Purchasing happens in-station, by the player, same as every other module purchase in the game; there's no known CAPI remote-purchase path for ship modules, so this was never a candidate for automation in the first place, consistent with `design-principles.md`.

## Feature D: Permit readiness check

For any system referenced by a build recommendation, a tour plan (see `exploration-triage-framework.md`), or an explicit player query, check whether the player currently holds the required permit, and if not, state how to acquire it (reputation threshold, mission chain, Community Goal reward, etc., per system).

**Status: scoped down, not blocked-pending-research anymore.** No source exists (as of this research pass) to confirm *current* held-permit status programmatically. The feature reduces to: state the unlock requirement for a given system (reputation/mission/CG — this part is straightforward reference content) without being able to confirm whether the player has already met it. Worth revisiting if Inara ever ships the permit feature it says is coming, or if a CAPI field for it turns up in future research.

## Open items

- **Pinned-blueprint tracking** (if ever wanted as a feature) — no data source exists; per `inara-api-notes.md`'s forum research, pinned blueprints have no journal event at all.
- **"Sweet spot" balancing logic** — how the assistant should weigh competing stats when the player asks for a balance rather than a single-purpose optimization is a UX/algorithm design question for build time, not resolved here.
- **Discount-awareness approximation** (Feature C) — decide whether to approximate "this looks like a good price" from EDDN data, or drop discount-awareness entirely since Inara's curated version isn't accessible.
