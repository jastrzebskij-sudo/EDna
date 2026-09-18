# Exploration Destination Hypothesis: Star Type as a Pre-Travel Filter

Direct follow-on request: *"Understanding where past success was had, what can we infer about future exploration destinations? ... look for discovery of pristine planetary rings - especially found around high value planets, and especially pristine metallic rings ... Are the systems containing such finds similar in some ways? Star types maybe? Something we could observe from outside the system to increase the probability of future discoveries? Same for high-value exobiological finds. ... formulate a hypothesis we could test by doing some exploration missions to validate it."*

This formalizes and supersedes an earlier, never-written-up offer from a previous round (referenced in `follow-up-todo.md`'s Exploration section as "star-type correlation for high-value bodies, bio-diversity hotspot pattern, rarest-codex-entry list") — this round re-derives the analysis from scratch with a full, systematic query pipeline rather than the earlier ad hoc pass, so treat this doc as the current, authoritative version rather than a continuation of unrecorded earlier numbers.

## The hypothesis

**Primary (arrival) star spectral type is a usable, pre-travel filter for exploration value.** Systems whose arrival star is class A, F, G, or K produce high-value planets, pristine rings (especially pristine metallic), and biological finds at 2-4x the rate of M-dwarf systems (which dominate casual travel by sheer frequency) and at 10x-to-near-infinite the rate of brown-dwarf/T Tauri systems (T, Y, L, TTS), which are close to barren of all three in this history. Star type is visible via EDSM/the galaxy map for any system already logged by another commander, without traveling there — making this a genuinely actionable pre-travel signal, not just a retrospective pattern.

A single combined ranking, derived below: **A > F > O > G > K >> M >> (B, brown dwarfs, T Tauri stars near zero)**.

## Methodology

Built directly from `journal.duckdb` (2,018,910 events, 1,559 sessions), independent of the `journal_report` tool's existing pipeline (this is a one-off analytical pass, not a report page).

**System attribution.** A large fraction of `Scan`/`ScanOrganic`/`CodexEntry` events in this journal (particularly pre-2018 ones) don't carry a `StarSystem` field directly on the event, so system context can't be read straight off the row. Reconstructed the same way `journal_deepdive.py` reconstructs ship/vehicle state elsewhere in this project: an ASOF LEFT JOIN against the nearest-preceding `FSDJump`/`Location`/`CarrierJump` event in the same session (`source_file`), which do always carry `StarSystem`.

**Primary star.** For each system, the "arrival star" is the `Scan` event with `StarType` present and `DistanceFromArrivalLS = 0.0` (the star you land in supercruise next to on arrival — this is what's visible on the galaxy map/EDSM before travel, independent of anything scanned in-system). 4,632 distinct systems have a known primary star type this way.

**High-value planets**: `Scan` events with `PlanetClass` in {Earthlike body, Water world, Ammonia world, Water giant, Gas giant with water/ammonia based life} — 1,486 total finds.

**Rings**: every ring entry in every `Scan` event's `Rings` array, carrying the host body's own `ReserveLevel` (Pristine/Major/Common/Low/Depleted — this is a property of the body, not the ring array element) and each ring's own `RingClass` (Rocky/Icy/MetalRich/Metalic). "Pristine metallic" = `ReserveLevel = PristineResources` AND `RingClass = eRingClass_Metalic`.

**Biological finds**: `CodexEntry` events with `SubCategory_Localised = "Organic structures"` (the real species-discovery bucket — a sibling `"Geology and anomalies"` subcategory under the same `Category_Localised = "Biological and Geological"` label was excluded, since that's geological curiosities, not life). `VoucherAmount` used as a rough per-find value proxy — this is a Codex first-discovery bonus, not a true species-rarity catalog value, so treat rankings built from it as directional, not precise.

**Host-body characteristics for bio finds**: `ScanOrganic` events (filtered to `ScanType = "Log"`, one row per distinct species logged) joined to the same system + `BodyID`'s own `Scan` event, to pull that body's `PlanetClass`/`AtmosphereType`/`Volcanism`/`SurfaceTemperature`/`SurfaceGravity`. This join only works for the modern journal format that carries `BodyID` (1,642 of 6,526 total `ScanOrganic` rows) — a real coverage gap, noted below, not hidden.

## Findings

### High-value planets by primary star type (systems visited ≥ 10)

| Star type | Systems visited | Systems w/ ≥1 HV planet | Hit rate |
|---|---:|---:|---:|
| A | 135 | 33 | 24.4% |
| F | 325 | 70 | 21.5% |
| G | 435 | 90 | 20.7% |
| K (Orange Giant) | 15 | 3 | 20.0% |
| K | 815 | 116 | 14.2% |
| B | 40 | 5 | 12.5% |
| O | 36 | 4 | 11.1% |
| DA (white dwarf) | 11 | 1 | 9.1% |
| M | 2,070 | 145 | 7.0% |
| TTS (T Tauri) | 275 | 13 | 4.7% |
| L | 158 | 2 | 1.3% |
| T | 189 | 0 | 0.0% |
| Y | 113 | 0 | 0.0% |

Breakdown by planet class (counts, primary-star rows only — 1,043 of 1,486 total HV finds have a known primary star): Water world is the single largest category (595 total), Earthlike body second (470), then the two "gas giant with life" categories and Ammonia world; M-primary systems still produce raw counts across all categories (since M is visited so much more often) but at a much lower per-system rate than A/F/G/K.

### Pristine rings by primary star type

All pristine reserve-level rings:

| Star type | Systems visited | Hit rate |
|---|---:|---:|
| O | 36 | 30.6% |
| F | 325 | 20.0% |
| G | 435 | 15.4% |
| B | 40 | 15.0% |
| A | 135 | 14.1% |
| K | 815 | 10.4% |
| M | 2,070 | 5.9% |
| L / T / TTS / Y / DA | — | 0-1.9% |

Pristine **metallic** rings specifically (the highest-value ring type, 90 finds across 48 systems):

| Star type | Systems visited | Hit rate |
|---|---:|---:|
| B | 40 | 7.5% |
| O | 36 | 5.6% |
| F | 325 | 5.5% |
| A | 135 | 3.0% |
| G | 435 | 2.3% |
| K | 815 | 0.9% |
| M | 2,070 | 0.1% |

Pristine-metallic rings skew noticeably further toward hot, massive stars (O/B/F) than the HV-planet pattern, which peaks at A/F/G. Host bodies are overwhelmingly gas giants (Sudarsky class I-IV, 67 of 90) plus some High Metal Content bodies (13) — not the HV planet classes themselves. **60% of pristine-metallic-ring systems (29 of 48) also contain a high-value planet** — a real, checkable combination, not incidental overlap given how rare each is independently.

### Biological finds by primary star type

| Star type | Systems visited | Hit rate | Avg. voucher (where n≥5) |
|---|---:|---:|---:|
| A | 135 | 14.8% | 11,406 cr (n=16) |
| B | 40 | 12.5% | — |
| F | 325 | 11.1% | 6,953 cr (n=32) |
| G | 435 | 10.8% | 6,818 cr (n=44) |
| K | 815 | 9.1% | 9,715 cr (n=79) |
| M | 2,070 | 6.5% | 8,200 cr (n=125) |
| O | 36 | 5.6% | — |
| T / L / TTS / Y | — | 0.9-2.1% | — |

Same shape as the other two categories. Average voucher is noisier (smaller samples per star type) and shouldn't be leaned on as hard as the hit-rate pattern, but A-type systems come out on top there too.

**A within-system nuance worth acting on**: every biological find's host body was a plain **Rocky body, High Metal Content body, Icy body, or Rocky Ice body** — never an Earthlike/Water/Ammonia world itself (those are non-landable/thick-atmosphere and don't carry surface bio signals in this data, consistent with how exobiology actually spawns in-game). So the right move in a promising system is a full body-by-body FSS/DSS pass, not just beelining to whichever planet the system map flags as visually striking.

**Atmosphere composition of the bio-host body** correlates with genus diversity in this data — CarbonDioxide atmospheres hosted the most distinct genera (14), then Ammonia (10), Water (9), Methane (7), Argon (7). This is a cheap **on-arrival** signal (visible from an FSS/DSS pass without landing), not a pre-travel one — worth stating as a second, later-stage filter once you're already in-system, distinct from the star-type filter that applies before you even leave.

Volcanism showed no clear lift in this data (15 distinct genera on non-volcanic hosts vs. 13 on volcanic ones) — but the sample is heavily lopsided (1,550 non-volcanic scans vs. 92 volcanic), so this isn't strong enough evidence either way and shouldn't be used as a filter.

### Multi-star systems

Roughly doubled the bio hit rate (4.2% in single-star systems vs. 8.8% in multi-star systems) but showed no meaningful lift for high-value planets or pristine rings. Most likely explanation: a multi-star system simply has more bodies in total to scan, not a special property of stellar multiplicity itself — flagged as a plausible confound, not built into the ranking below, since it wasn't tested independently of body count.

### Combined "jackpot" ranking

Scoring each system by how many of the three categories (HV planet / pristine ring / bio find) it hit, and normalizing by how often each star type was actually visited:

| Star type | Systems visited | Jackpot rate (2+ categories) |
|---|---:|---:|
| A | 135 | 15.6% |
| F | 325 | 14.8% |
| O | 36 | 13.9% |
| G | 435 | 13.1% |
| K | 815 | 8.1% |
| B | 40 | 5.0% |
| M | 2,070 | 3.6% |
| everything else | — | ≤0.6% |

## Caveats (stated plainly, since these bound what a validation trip actually tests)

- **Correlation, not causation, and not free of confounds.** This is derived entirely from your own 9 years of play — if your past self already gravitated toward certain star types when specifically hunting for good finds (rather than choosing destinations at random), that selection bias would inflate exactly this pattern independent of any real astrophysical relationship. The hypothesis is worth testing precisely because of this risk, not despite it.
- **Coverage isn't uniform across the dataset.** Older-format journal entries (roughly a third of `Scan` events) predate fields like `BodyID`/`WasDiscovered`, so the bio-host-characteristics join only covers the modern-format subset (1,642 of 6,526 total `ScanOrganic` rows). The direction of the pattern is consistent enough across categories that this is unlikely to flip the conclusion, but it isn't the complete dataset.
- **Voucher amount is a rough value proxy for bio finds**, not a true species-rarity catalog value — good for a directional hit-rate pattern, not precise enough to rank individual species.
- **Sample sizes are uneven by star type** — the rarer classes (O, B, DA, K Orange Giant) have wide-swinging rates on n<50, so the A/F/G/K >> M >> brown-dwarf pattern is the load-bearing conclusion; don't over-read fine distinctions within the top tier (e.g. "A is definitively better than F") from this sample alone.

## A concrete validation plan

Use EDSM to pre-filter unexplored systems within practical jump range by primary star spectral class (A/F/G/K), and fly a batch of those specifically for this test, alongside a comparable-sized batch of M-dwarf systems as a control (M dwarfs being the natural baseline, since they're what most undirected travel already passes through). Log hit rate for each of the three categories per batch and compare against the rates above:

- If A/F/G/K systems come in anywhere near the 2-4x lift over M dwarfs shown here, the hypothesis holds up on fresh data, not just the data it was built from.
- If the lift washes out on a fresh sample, that's evidence the original pattern was more about where past-you chose to explore than about the stars themselves — a genuinely useful negative result, and worth recording either way.
- Within a promising system, scan every body (not just the obviously striking one) given the finding that bio life and "flashy" planet classes don't share a body in this data.

Not yet built into any tool — this is a manual travel-planning heuristic for now. If it holds up under validation, it would be a natural addition to `exploration-triage-framework.md`'s system-classification tier ("known & uninteresting / unscanned / flagged interesting") as a *pre-arrival* signal ahead of any in-system scan data, which that doc doesn't currently have.
