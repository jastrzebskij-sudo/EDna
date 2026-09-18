# Surface Navigation Assist

A recommendation-format capability (see `design-principles.md`) for planetary-surface navigation — ship/SRV heading, descent angle, and settlement-placement planning. Distinct from every other worked example so far in that it involves **no automation-boundary question at all**: nothing here touches game input, so there's no bookend/manual split to work out — it's pure computation off data the assistant already has, stated as a recommendation the player acts on with their own hands (steering, throttle).

## Data inputs

- **Current position**: `Status.json` — `Latitude`, `Longitude`, `Heading`, `Altitude` (populated when on/near a planetary surface, per the Status File docs).
- **Body radius**: journal `Scan` event's `Radius` field (meters) — needed to do great-circle math on the correct sphere size for whichever body you're on.
- **Target coordinate(s)**: player-supplied (typed, a saved bookmark/POI, or a previously scanned settlement/site location).

Approximation adopted: **treat landable bodies as spheres**, not oblate spheroids. Reasonable simplification matching how in-game surface nav almost certainly works; revisit only if it turns out to matter in practice.

## Calculations

### 1. Bearing to a target coordinate
Standard great-circle initial-bearing formula:

```
θ = atan2( sin(Δλ)·cos(φ2), cos(φ1)·sin(φ2) − sin(φ1)·cos(φ2)·cos(Δλ) )
```
where φ1/λ1 = current lat/long, φ2/λ2 = target lat/long (radians), θ normalized to 0-360°.

**Output shape**: "Recommended bearing: 047°, based on great-circle heading to 12.34/-56.78 (great-circle distance: 8.2 km)." — stated action + criteria, per the recommendation-format pattern.

### 2. Descent angle
Given current altitude and horizontal distance to target:

```
descent_angle = atan2(altitude, horizontal_distance)
```

Horizontal distance can use the great-circle formula (haversine) for accuracy, or a flat-plane approximation at short range — only worth the spherical treatment if the target is far enough that curvature meaningfully matters (uncommon for a single approach/descent).

**Output shape**: "Recommended descent angle: 12° below horizontal, to reach target altitude 0 over the remaining 3.1 km."

### 3. Settlement placement near an anchor coordinate
The inverse problem — "destination point given start point, bearing, and distance," also standard great-circle math:

```
φ2 = asin( sin(φ1)·cos(d/R) + cos(φ1)·sin(d/R)·cos(θ) )
λ2 = λ1 + atan2( sin(θ)·sin(d/R)·cos(φ1), cos(d/R) − sin(φ1)·sin(φ2) )
```
where d = desired distance, R = body radius, θ = chosen bearing per settlement.

Given an anchor coordinate, a desired spacing, and a count, compute each settlement's coordinate at a chosen bearing/distance from the anchor, arranged in whatever pattern makes sense (ring, line, triangulated cluster).

**Output shape**: a list of candidate coordinates, each stated with its bearing + distance from the anchor ("Settlement A: 12.50/-56.70, bearing 030° / 5.0 km from anchor; Settlement B: bearing 150° / 5.0 km from anchor; ...").

## Why this is the cleanest capability so far

Every other worked example (carrier jumps, limpets, exploration triage) required splitting an action into an approvable bookend and a manual-only interior. This one doesn't need that split — there is no automatable input anywhere in it, because it never issues an input at all. It's the purest form of the recommendation pattern: state the number, state the reasoning, the player flies it themselves.

## Open items

- Pattern logic for multi-settlement placement (ring vs. line vs. triangulated cluster, and how spacing/count map to a specific arrangement) isn't decided — a build-time UX question, not a principles one.
- Whether to expose great-circle vs. flat-plane distance/bearing as a user-visible toggle, or just pick automatically based on distance, is also a build-time call.
