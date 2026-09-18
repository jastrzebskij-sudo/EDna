# Exploration Triage & Assist Framework

Applies the automation-boundary principles in `design-principles.md` (see especially the three tests, the recommendation-format section, and the system-arrival worked example) to the specific case of deciding what to do on arrival in a system while exploring.

**What actually differentiates this from existing tools** (EDDiscovery, Elite Observatory, ED Materials Helper, etc.): those surface raw data and leave interpretation to the player. Every "AI recommendation" row below is not a data dump — it's a stated action plus the criteria behind it ("recommended: skip, based on already-surveyed + no flagged bodies" / "recommended: prioritize body 4 first, based on bio-signal count + shortest backtrack"). The player can disregard or override any of it; nothing here auto-executes on its own recommendation.

## Triage: classifying the system, before any action

Before the player does anything, the assistant can classify the system using data it already has — journal history, EDSM lookups, bundled value-heuristics (Canonn/EDAstro-style body-value tables) — pure information, zero game-state touch, always allowed regardless of the automation-boundary rule:

1. **Known & uninteresting** — already fully surveyed (by the player or the EDSM community) with no outstanding high-value bodies.
2. **Unscanned** — no discovery-scan data yet, this trip or ever.
3. **Flagged interesting** — scan data (this trip's FSS, or prior EDSM/journal data) shows indicators worth deeper investigation: ELWs, water worlds, terraformable candidates, notable bio-signal counts, high first-discovery/mapping value, etc.

## Per-classification handling

### 1. Known & uninteresting → skip
- **AI recommendation**: "Already surveyed, nothing outstanding — continue on."
- **Automatable bookend**: none needed, there's nothing to press.
- **Stays manual**: whether to still honk anyway for exploration-data credit is the player's own call; the assistant informs it, doesn't override it.

### 2. Unscanned → preliminary survey
- **Automatable bookend** (single-press macros, test 1): discovery scan ("honk"), FSS mode-entry toggle.
- **Stays manual** (test 3): flying to gain distance from the star; actually running the FSS scan/tuning — this is the gameplay itself, not a formality.
- **AI recommendation**: once the player's own FSS pass populates journal data, parse the resulting body list and flag what's worth a closer look, prioritized by whatever value signal is available.

### 3. Flagged interesting → prepare in-depth tour
- **AI recommendation**: a prioritized itinerary — which bodies, why (bio signals, notable terrain, first-discovery value), a suggested visiting order to minimize backtracking (see "Route sequencing" below).
- **Automatable bookend** (test 1): a pre-tour checklist bundling discrete toggles the player would do anyway before a tour — limpet/probe loadout, SRV/suit loadout if landing, relevant sensor toggles. Same "bundle of instant presses" pattern as the mining limpet swarm.
- **Stays manual** (test 3): all flying between bodies, DSS/probe firing (itself a skill-based minigame, not a discrete input), landing, on-foot exploration.

#### Route sequencing (named capability within the tier-3 recommendation)

Multi-body-of-interest systems can cause real back-and-forth transit if visited in scan order or list order rather than a sensible physical sequence. A pilot can eyeball an efficient path in the in-game orrery view, but the more common UI is a flat list of bodies sorted by current distance — which doesn't reflect the actual geometry between bodies of interest. Worth naming as its own recommendation: **the assistant computes a suggested visiting order and states it with its rationale** ("recommended order: 2 → 5 → 3, based on minimizing backtrack across the system" or similar) — same recommendation-format pattern as everything else here, purely informational, the player still flies every leg themselves.

Honest framing per the discussion that produced this: the time actually saved by an optimal order over a reasonable manual guess is often small. The value is more in *feel* — a system that visibly reasons about the geometry reads as more sophisticated than one that doesn't, even when the practical payoff is modest. Worth building for that reason, not because it's solving a large problem.

**Open technical question, not yet resolved**: journal `Scan` events expose `DistanceFromArrivalLS` — a scalar distance from the arrival star — not each body's full 3D position relative to the others. Two moons on opposite sides of the same planet, for instance, look identical by that scalar alone. A genuinely accurate "avoid backtracking" route needs real 3D positions, which means either:
  - reconstructing them from each body's orbital elements (semi-major axis, inclination, periapsis argument, ascending node, mean anomaly, orbital period) via actual orbital mechanics, evaluated at the current in-game time — doable, but real work, not a lookup; or
  - a cheaper approximation that just orders by `DistanceFromArrivalLS` (roughly correct for systems where bodies are arranged in outward "shells," which is most of them, but wrong for same-orbit satellite clusters).
  Which approach is worth the complexity is a build-time decision, not a principles one — flagging it here so it isn't assumed to be a trivial sort when this actually gets built.

## Net shape

The assistant's exploration role, at every tier: **triage and recommend for free** (pure information) → **bundle the discrete button-press housekeeping** around each phase (approved, test 1) → **hand every bit of actual flying and scanning back to the player** (test 3, never automated, no matter how routine it feels). This is the same split verdict reached for the basic system-arrival sequence in `design-principles.md`, just extended to cover the higher-value "is this worth a deeper look, and if so what's the plan" decision point.

## Open items

- Exact value-heuristic to use for "indicators of interest" in tier 3 isn't decided yet — candidates are Canonn's or EDAstro's body-value data, or a simpler home-grown heuristic off journal `Scan` event fields (terraformable flag, body class, bio-signal counts from `SAASignalsFound`). Revisit once we're actually building this.
- Whether the pre-tour checklist (tier 3 bookend) should be one combined macro or several smaller ones (limpets vs. loadout vs. sensors) is a UX question for whenever this gets built, not a principles question.
