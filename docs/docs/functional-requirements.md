# Journal Report Tool — Functional Requirements

Tech-stack-agnostic capture of what the tool must do, extracted directly from
the current implementation (DuckDB + pandas + Plotly + a static-HTML/iframe
shell), so a rewrite onto a different stack (e.g. FastAPI + MySQL + JS
frontend) can be checked against this rather than against the old code. This
is the "what," not the "how" — implementation notes are called out
separately where they matter.

## 0. Non-negotiable properties

- **No AI/Claude involvement needed at runtime.** Pure code; a rewrite must
  keep this true.
- **Single user, single local machine.** The data source is one person's
  `journal.duckdb` (or successor DB) on their own PC. Not a hosted multi-user
  service.
- **Read-only against game data.** This tool only reads/analyzes; it never
  writes back to the game or the journal files.
- **Every heuristic/flag must show its raw evidence.** Nothing in this tool
  is allowed to assert a conclusion without the underlying raw field(s)
  (event names, Slot/Item strings, timestamps) visible next to it, so the
  user can check or override it. This is a hard requirement across every
  tab, not a nice-to-have.
- **Correctness bugs found so far must not regress.** See section 5.

## 1. Core domain model (shared by every tab)

### 1.1 Sessions
A session = one journal source file. For each: start/end timestamp (min/max
event timestamp), duration in hours, event count, month, day-of-week, hour
of day. A "valid" session for duration-based analysis is `0 < duration_hours
< 12` (excludes zero-length and multi-day/crashed-open outliers).

### 1.2 Event categorization
Every event maps to exactly one of ~13 categories: Combat, Exploration
(transit), Exploration (deep), Trading, Mining, Social, Passengers/Missions,
Engineering, Colonisation, Travel, Ship management, Powerplay (any event
name starting with "Powerplay"), Ambient (excluded from activity-mix views
by default), Other (fallback for unmapped event types — the map is not
exhaustive across all ~214 distinct event types seen in a 10-year corpus).

**Exploration is deliberately split into two buckets**, not one:
- *Transit*: passive/automatic scanning while flying through on the way
  somewhere (FSS honks, auto-scans on jump-in).
- *Deep*: deliberate exploration effort (detailed/manual scan, selling
  exploration data, surface scans, exobiology).
The `Scan` event's own `ScanType` field decides which bucket it falls into
(`AutoScan` → transit, anything else, e.g. `Detailed`/`NavBeaconDetail` →
deep) — not a guess from the event name alone.

A fixed color-per-category map is shared across every chart in the whole
report so the same category is visually identifiable everywhere.

### 1.3 Ship attribution
Every event is attributed to "whichever ship's `Loadout`/`LoadGame` was most
recently seen at or before that event's timestamp" (a nearest-preceding-value
join, e.g. DuckDB's ASOF JOIN; any equivalent "last value at or before this
timestamp" mechanism is required — a MySQL port needs its own way to do
this, since MySQL has no ASOF join primitive).

- Display name: the ship's custom `ShipName` if non-blank after trimming
  whitespace (an all-whitespace name must NOT survive as a "real" name —
  a real bug that produced blank rows), else `"{ShipType} [{ShipIdent or
  ShipID}]"`.
- An event before the very first `Loadout` in the whole journal is
  attributed to a synthetic `"Unknown ship (before first Loadout)"` bucket.
- SRVs and on-foot suits also emit `Loadout`/`LoadGame` (with a `ShipID`) and
  get swept into this same attribution mechanism — they must be excluded
  from every "real ship" fleet view via a name-substring filter (matches:
  `testbuggy`, `utilitysuit`, `explorationsuit`, `tacticalsuit`, and the
  "before first Loadout" bucket itself). Not applied globally — only to the
  fleet-overview/idle/coverage/flight-hours/distance views where showing a
  buggy or suit next to real ships would mislead.

### 1.4 Vehicle state (SHIP / SRV / FOOT)
A small state machine over 5 boundary event types, evaluated in event order
within a session:
- `LaunchSRV` → SRV
- `DockSRV` or `SRVDestroyed` → SHIP
- `Disembark` → FOOT
- `Embark` → SRV or SHIP depending on that event's own `SRV` flag (Embark
  fires both getting into the ship and into the SRV)
- Default (no boundary event yet in the session) → SHIP

**Every combat-adjacent metric (kills, deaths, near-death, hull damage) must
filter to vehicle_state == SHIP** before attributing it to "this ship's"
combat record. This is a confirmed, previously-shipped bug fix (see 5.1) —
a rewrite must not reintroduce it.

### 1.5 Module role recognition (for fit-vs-usage checks)
A conservative, ordered substring-match list on the internal Elite `Item`
name, first match wins:
shield generator, shield cell bank, fuel scoop, detailed surface scanner,
prospector/collector/fuel-transfer/repair limpet controller, cargo rack,
passenger cabin, docking computer, heat sink launcher, shield booster,
chaff launcher, electronic countermeasure, caustic sink launcher, point
defence turret, kill warrant scanner, manifest scanner, then a generic
`"hpt_"` fallback labeled "Hardpoint-mounted module" (actual weapons).
**Order matters**: utility-mount items (heat sink, shield booster, chaff,
ECM, etc.) share Elite's `hpt_` prefix with real weapons internally, so they
must be matched by their specific name *before* the generic `hpt_` fallback,
or they get mislabeled as weapons (a real, previously-shipped bug).
Unrecognized items are simply not surfaced (conservative by design — no
"unknown module" catch-all).

### 1.6 Mission windows (for surface-activity attribution)
A mission is "active" from `MissionAccepted` to the first of
`MissionCompleted`/`MissionFailed`/`MissionAbandoned`; missions never
resolved in the journal (~1%) fall back to their own `Expiry` timestamp as
an assumed end. An SRV/on-foot excursion counts as "under a mission" if its
time span overlaps *any* active mission window at all — stated explicitly
as a real limitation (co-occurrence, not proof of causation) rather than
glossed over.

## 2. Per-tab requirements

### 2.0 Overview
Static descriptive landing content: dataset summary (source path, session
count, event count, ship count, ships-with-known-loadout count) and a
one-line description of each other tab. No computation beyond those top-line
counts.

### 2.1 Gameplay Analysis
- Monthly play frequency (session count) + estimated playtime (summed
  session duration), as a combo chart, with vertical reference lines at
  known major game-update dates (a maintained list: Horizons, The
  Engineers, Beyond Ch.1, Fleet Carriers, Odyssey, Trailblazers/
  Colonisation).
- Session-start heatmap: day-of-week × hour-of-day, all years combined.
- Fleet-wide activity mix over time: monthly share-of-events by category
  (Ambient excluded), stacked/area, with the same update-date reference
  lines. Needs an interactive month-hover breakdown showing every category's
  share for that month (native chart tooltips proved insufficient at ~12
  categories — see 5.3 — a rewrite may find a cleaner native solution but
  must preserve "hover a month, see every category's share at once").
- Session-length histogram, restricted to the 0–12h valid-session window.
- Per-event-type monthly trend explorer: user picks one of the top 40 most
  frequent event types (by total count) and sees its monthly trend line,
  with the same update-date reference lines.

### 2.2 Ship Profile Analysis
- **Fleet usage overview**: every identified ship, ranked by real
  flight-hours (see 2.9 methodology — NOT raw event count, since Combat
  alone emits ~4–30x more events/hour than most other categories and would
  make combat-heavy ships always "win" regardless of real usage), log-scale,
  colored by each ship's single most common ("dominant") activity category.
- **Distance traveled per ship**: total real light-years jumped (from
  `FSDJump`'s own `JumpDist` field, not inferred from event density),
  log-scale, ships with ≥1 jump only.
- **Idle-ship check**: every ship, sorted longest-untouched first
  (days since last event), with flight-hours, avg hours/trip, total ly,
  dominant activity, last-active date — a "candidates to sell/store/
  repurpose" list, explicitly framed as a starting point, not a verdict.
- **Activity coverage**: for each activity category, which single ship
  contributes the most events to it and what share of the category that one
  ship accounts for ("concentration"). Concentration < 25% (configurable
  threshold) → flagged "no dedicated ship, spread across the fleet" — a gap
  signal, not a verdict.
- **Kills by ship** (NPC vs. player split) and **Deaths by ship** (NPC vs.
  player vs. Self/Accident split): both scoped to vehicle_state == SHIP only
  (see 1.4/5.1), with an "excluded" column showing how many kills/deaths were
  earned/suffered in an SRV or on foot instead, rather than silently
  dropping them.
  - NPC vs. player kill split: `Bounty`/`FactionKillBond` = NPC-only
    vouchers; `PVPKill` = player-only (and rare — confirm actual rarity
    against the live DB, don't hardcode the historical count).
  - Death opponent-type split (3-way, unique to deaths): a `Died` event's
    own shape decides it — a `Killers` array with entries named `"Cmdr
    <name>"` → Player; a singular `KillerName`/`KillerShip` → NPC; neither
    present → Self/Accident (collision, terrain, fuel-scoop overheat, etc.
    — the journal doesn't record the specific cause, only that nothing else
    killed the player).
- **Activity composition by ship** (top 20 by event volume): stacked
  share-of-events by category per ship.
- **Per-ship activity mix over time** (all ships, dropdown-selectable):
  monthly share-of-events by category for one ship at a time, with the same
  interactive-hover requirement as 2.1's activity-mix chart.
- **Fit-vs-usage findings table**: for every ship with a known (most recent)
  `Loadout`, cross-reference its fitted modules (via 1.5's role recognition)
  against usage evidence counts for that ship. Flag rules (evidence key →
  module role → zero-evidence message / rare-evidence message + threshold):
  - zero combat events + Shield Generator or Shield Cell Bank fitted →
    "likely unnecessary"; rare (<1% of that ship's events) → "worth
    reviewing."
  - zero `FuelScoop` events + Fuel Scoop fitted → "likely unnecessary"; rare
    (<0.5%) → "worth reviewing."
  - zero deep-exploration events + Detailed Surface Scanner fitted →
    "likely unnecessary"; rare (<1%) → "worth reviewing."
  - zero combat events + any generic hardpoint-mounted module → "likely
    unnecessary" (caveated: could be a utility mount misclassified, since
    only well-recognized utility items are excluded from this generic
    bucket); rare (<1%) → "worth reviewing."
  Every flagged row must show the ship, module role, raw Slot string, raw
  Item string, severity ("Likely unnecessary[, engineered]" / "Worth
  reviewing"), and the human-readable reason. Ships with a known loadout but
  no flags are listed separately as "no flags raised for."
  This explicitly does **not** compute an optimal replacement fit (that
  needs real Coriolis-style engineering-modifier math, out of scope here).

### 2.3 Play Patterns
- **Event tempo by category**: events-per-active-hour, per category —
  the direct explanation for why raw event counts are a bad usage metric
  (see 2.2).
- **Session duration vs. net credits earned**, scatter, log y-axis (colored
  by session's dominant category), plus the two correlation coefficients
  (duration-vs-total-credits, duration-vs-credits/hour) stated in the title
  — the explicit point being that longer sessions don't reliably earn more
  or earn faster.
- **Credit efficiency by session's dominant activity**: sessions count, avg
  duration, avg net credits, avg and *median* credits/hour (median called
  out specifically because rare huge-payday sessions skew the mean).
- **Top 5 most lucrative sessions** and **top 5 longest sessions** (0–12h
  valid window), each as a simple list: date, duration, net credits,
  dominant category. Session credit totals include any voucher/bulk-data
  redemption landing in that session even if earned earlier — stated
  explicitly as a caveat (exploration/exobiology data can be banked across
  many sessions and cashed in at once).
- Net-credits-per-session computation (shared with 2.7's spotlights):
  summed `credit_delta` across `Bounty` (TotalReward), `FactionKillBond`
  (Reward), `MissionCompleted` (Reward), `MarketSell` (+TotalSale),
  `MarketBuy` (−TotalCost), `SellExplorationData` (BaseValue+Bonus),
  `MultiSellExplorationData` (TotalEarnings), `RedeemVoucher` (Amount), and
  `SellOrganicData` (sum of each BioData entry's Value+Bonus) per session.

### 2.4 Combat Analysis
- **Most common bounty-kill opponents, fleet-wide** (top 20 by kill count,
  from `Bounty` vouchers, vehicle_state==SHIP only).
- **Opponent mix per ship** (top 8 ships by kill count × top 12 opponent
  types fleet-wide).
- **Every recorded ship-combat death**, full table: date, ship, killer ship
  (or "unrecorded"), killer rank, ship's dominant activity,
  "overconfidence flag." `is_ship_combat` deaths only (excludes on-foot/SRV
  losses and Self/Accident deaths). Overconfidence = ship-combat death where
  the ship's own dominant activity category is *not* Combat — a narrow,
  checkable "this ship got in over its head" signal, not a vibes judgment.
- **Interdiction exposure by ship** (top 15): times interdicted, times
  submitted (didn't fight/flee first).
- **Near-death events by ship** (top 15): count of `HullDamage` events with
  `Health < 0.25`, vehicle_state==SHIP and `PlayerPilot==true` only — an
  independent "got into real danger" signal regardless of whether the ship
  was actually lost.
- **Overconfidence instances narrative list**: every flagged
  overconfidence death spelled out in prose (date, ship, its usual role,
  who destroyed it and their rank).
- All counts here are raw totals, not per-hour rates — cross-reference with
  2.2's flight-hours for a rate if needed (stated explicitly, not silently
  assumed obvious).

### 2.5 Economy Analysis
- **Credits per active hour: trading vs. mining**, single comparison bar.
  "Active hour" = distinct hour-buckets containing at least one event of
  that category.
- **Most profitable pure-trade commodities** (top 15 by estimated total
  profit = total sale − total cost).
- **Most valuable mined commodities** (top 15 by estimated total value =
  units refined × that commodity's own historical average sell price).
- **Best-earning ship per activity**: top 10 trading ships by estimated
  trade profit, top 10 mining ships by estimated mining value, side by side.
- **Critical correctness rule, must be preserved exactly**: `MarketSell`
  does not record whether the sold cargo was bought (real trading) or mined
  (free) — so any commodity that is *also* mined by this player (matched via
  a normalized-string join against `MiningRefined`'s own commodity names)
  must be excluded from "pure trading" profit entirely. Otherwise mining
  income silently inflates trading-profit figures (confirmed to overstate
  by ~80x in one real case — painite: 10 units ever bought vs. 16,321 sold).
  This deliberately *understates* trading profit for the handful of
  commodities that are legitimately both bought/sold and mined (gold,
  silver, palladium, platinum, tritium) — the journal has no per-unit
  provenance to split them, so "count it all as mining" is the conservative,
  defensible choice, not a guess.
- **Per-ship trade profit must be restricted to the same "pure trade"
  commodity set** used in the fleet-wide figure (not just "exclude mined
  commodities" — must also exclude commodities with literally zero recorded
  buys, e.g. mission-reward/salvage/colonization cargo picked up free then
  sold, which would otherwise count as pure per-ship profit while not
  appearing in the fleet-wide reconciling total). The fleet-wide and
  summed-per-ship totals for pure trade profit must reconcile (a real bug
  was caught exactly because they didn't).
- Per-ship trade profit is attributed to whichever ship did the buying or
  selling — cargo bought on one ship and sold from another (fleet-carrier
  transfer) legitimately shows as a loss on the buyer and a gain on the
  seller. State this explicitly rather than "fixing" it — it's a correct
  description of which ship handled which side of the transaction, not a
  bug.

### 2.6 Exploration Deep Dive
- **Most profitable systems by exploration-data sale value** (top 20).
  A bulk sale (`SellExplorationData`/`MultiSellExplorationData`) lists
  several systems together with one combined payout — split the payout
  evenly across the listed systems (stated as an approximation, since the
  journal doesn't itemize per-system value within a bulk sale). Flag systems
  containing an exotic star type (see below) distinctly in the chart.
- **Most valuable systems for exobiology** (top 20, from `ScanOrganic`
  scans joined to the player's own historical average sale value per
  species — `ScanOrganic` and `SellOrganicData` are separate events with no
  direct reference to each other, so this is an estimate, not an exact
  per-system sale figure).
- **Highest-value biological species analysed** (top 15 by the player's own
  average sale credits per sample).
- **First-time Codex discoveries by subcategory** (count of `IsNewEntry`
  Codex entries, grouped by `SubCategory_Localised`).
- **Discovery-type × primary-star-type hit-rate table**: for each of 4
  discovery types (High-value planet [Earthlike/Water/Ammonia/Water giant/
  gas giant with water or ammonia based life], Pristine ring (any),
  Pristine metallic ring, Biological find [any "Organic structures" Codex
  subcategory]), the % of systems visited with a given *primary* (arrival)
  star type that produced at least one find of that type.
  - "Primary star" = the star scanned at `DistanceFromArrivalLS == 0` in
    that system.
  - System boundary/attribution for this table must be timestamp-based
    (nearest preceding `FSDJump`/`Location`/`CarrierJump` with a
    `StarSystem` field in the same session), **not** any precomputed
    system-address lookup — the precomputed lookup misses ~7–11% of
    pre-2018-format events, which matters because this table spans full
    history.
  - **Column layout is a fixed whitelist**: the 7 standard main-sequence
    classes (O, B, A, F, G, K, M) each get their own column; every other
    star type actually visited (giants, brown dwarfs, white dwarfs, T Tauri,
    neutron stars, black holes, etc.) pools into a single "Other" column,
    regardless of how many times it was visited. Nothing visited is
    dropped — "Other" still counts toward every hit rate — but the column
    count must stay fixed at ≤8 (not scale with how many exotic star types
    exist in the data; two earlier column-selection approaches were tried
    and rejected for producing unreadably wide/overlapping tables — see
    5.2). The pooled ("Other") hit rate must be computed at the system
    level (union of member star types' systems) — never as an average of
    the member star types' individual rates, since a rarely-visited star
    type would otherwise get equal weight to a heavily-visited one. Each
    column header must show its own visited-system count (n=), since a
    small n makes that column's percentage noisy — the table is meant to be
    read for the broad A/F/G/K-vs-M-vs-everything-else shape, not small
    differences within it.
- **Notable/unusual finds narrative**: Thargoid Codex encounters (listed
  chronologically with date/name/system), rare stellar phenomena visited
  (neutron star, black hole, carbon star, S-type star, orange giant, red
  giant, the two white-dwarf subtypes — count + first-seen date each), and
  a callout for any single-session outlier sale that's really a
  multi-session accumulation cashed out at once (framed honestly as "not one
  incredible session," see 2.7's carryover check for the general mechanism).
- Whether exotic-star-type systems earn a real exploration-credit premium
  (mean credits for systems with vs. without an exotic star, among the top
  60 exploration-credit systems) is reported as an observed comparison, not
  asserted as fact either way.

### 2.7 Surface Activity
- **Total on-foot and SRV hours**, split into "under an active mission" vs.
  "no active mission (free choice)," as a stacked bar with % labels.
- **Activity-category composition**, faceted by (state × mission-status) —
  4 facets: on-foot/mission, on-foot/free, SRV/mission, SRV/free — stacked
  share-of-events per facet. Needs a few on-foot/SRV-specific category
  overrides not used anywhere else in the report (CommitCrime→Combat;
  BackpackChange/CollectItems/DropItems/CollectCargo/ShipLocker/Backpack→
  Looting/Inventory; SuitLoadout→Ship management; DatalinkScan→Exploration
  (deep); LaunchSRV/DockSRV/Disembark/Embark/Touchdown/Liftoff→Travel) —
  scoped to this tab only, not the shared category map.
- **Most common mission types overlapping an excursion**, on-foot and SRV
  side by side (top 10 each), with mission names normalized (strip
  `Mission_`/`MISSION_`/`Chain_` prefixes and `_name` suffix) to a readable
  base name.
- **Excursion-to-mission overlap rule**: an SRV/on-foot span counts as
  "under a mission" if it overlaps *any* mission window (see 1.6) at all —
  a real limitation stated on the page, not hidden.
- **Vehicle-state span computation**: each boundary event starts a span
  running to the *next* boundary event in the same session (session end as
  fallback for the last span) — deliberately NOT based on in-span event
  density, since on-foot events are comparatively sparse and density-based
  timing would badly undercount short excursions. Zero-duration spans (two
  boundary events logged in the same second) must be dropped, not left to
  distort per-span averages.
- Narrative summary of the headline finding (must be recomputed from the
  live data, not hardcoded): what % of on-foot time vs. SRV time overlaps a
  mission, and what that time is actually spent on.

### 2.8 Session Spotlights
Per-session deep dive on the same top-5-most-lucrative-sessions list as
2.3 (same 0–12h valid-session filter, same net-credits ranking). For each
of the 5 sessions:
- **Header block**: date, net credits, duration, dominant activity,
  credits/hour, every ship flown (with event counts), distinct systems
  visited (from `FSDJump`/`Location`/`CarrierJump`, in visit order, capped
  preview list) with a jump count.
- **Predominant events this session** by category (bar chart).
- **What earned the credits**, bucketed into exactly 4 categories:
  - "Mission reward" — `MissionCompleted` only (unambiguous).
  - "Combat voucher" — `Bounty`/`FactionKillBond` (earned by fighting, not
    tied to a specific mission).
  - "Trading/other voucher" — net `MarketSell`−`MarketBuy`,
    `RedeemVoucher`.
  - "Bulk exploration/exobiology data" — `SellExplorationData`,
    `MultiSellExplorationData`, `SellOrganicData` — gets its own carryover
    check (below) since this category alone can span many real-world
    sessions.
- **Carryover ("was this actually earned this session") check** for the
  bulk-data bucket:
  - For exploration-data sales: compare the systems *named in the sale
    event itself* against systems actually visited in this session; any
    named system not visited this session is flagged as carried-over data,
    with named examples.
  - For exobiology proceeds: any `SellOrganicData` proceeds in a session
    with zero of its own `ScanOrganic` events is flagged as carried-over.
  - When nothing is flagged, state explicitly that the session's
    exploration/exobiology proceeds line up with this session's own
    activity — don't just omit the note.
- **Combat opponent breakdown** (opponent ship type, kill count, total
  reward) — shown only if the session had any `Bounty` kills; omitted
  entirely otherwise (not every top session is combat-driven).
- **Exploration detail** (scan-type counts, distinct exobiology species
  scanned, any brand-new [`IsNewEntry`] Codex entries logged) — shown only
  if the session has any of these; omitted otherwise.

## 3. Cross-cutting UI/serving requirements (current shell, not necessarily
   the new stack's mechanism, but the underlying needs any replacement must
   satisfy)

- A single entry point presenting all tabs together, tab bar always visible
  while a tab's own content scrolls independently (a fixed-position sidebar
  + independently-scrolling content area, or equivalent).
- A visible, working "Refresh"/re-sync action that picks up new data without
  restarting the whole app, returning the user to the tab they were on.
- No stale data ever served after a refresh/rebuild (three-layer no-cache in
  the current implementation: HTML meta tags, HTTP headers, and
  cache-busting query params — the underlying requirement is just "never
  show old data silently").
- Every chart/table with more categories than fit a native tooltip
  comfortably needs a full breakdown visible on hover/interaction (not just
  the single nearest data point) — see 2.1/2.2's activity-mix charts.

## 4. Explicitly out of scope (do not build unless separately requested)

- Optimal-fit/engineering-modifier replacement recommendations (needs
  Coriolis-style stacking/diminishing-returns math — see
  `ship-build-advisor.md`).
- Any write path back into the game, the journal files, or any Elite
  Dangerous account service.
- Multi-user support, hosted/remote deployment, authentication.
- Live-tailing the journal while the game is running (see
  `data-architecture.md` — this tool always analyzes a DB that's already
  been ingested up to "now").

## 5. Correctness fixes that must not regress in a rewrite

1. **Vehicle-state contamination** (the "Heart of Gold" bug): a ship's
   combat/kill/death/near-death record must only include events where the
   player was actually IN that ship at the time — not events earned/suffered
   in an SRV or on foot launched from it, and not misattributed to whatever
   ship's `Loadout` happened to be most recent while the player was
   elsewhere. Confirmed to have affected 18% of combat-type events and 23%
   of near-death events fleet-wide before the fix.
2. **Star-type hit-rate table column explosion**: must stay a fixed ≤8-column
   layout (7 main-sequence classes + "Other"), never one column per star
   type actually seen in the data (produced a 21-column unreadable table
   twice before the whitelist approach was adopted).
3. **Category-mix chart legend/tooltip**: with ~12 categories, a native
   "hovermode=x unified"-style tooltip is too tall/collides; a native
   "closest"-style tooltip doesn't show the full month's breakdown at all.
   Whatever replaces Plotly must solve "hover a point in time, see every
   visible category's share at once," not silently regress to a
   single-series tooltip.
4. **Empty-DataFrame column loss**: (pandas-specific, but the *general*
   requirement survives any stack) filtering an empty result set must never
   silently drop columns/fields that downstream code expects to exist —
   guard for the zero-rows case explicitly rather than assuming "the real
   database always has at least one row of X."
5. **Pure-trade-profit reconciliation**: fleet-wide pure-trade profit and
   the sum of per-ship pure-trade profit must always reconcile to the same
   total (same commodity-exclusion rule applied identically in both
   places) — this is a cheap, valuable regression check to keep running.
6. **File-name/whitespace edge cases**: a ship's custom name that is
   whitespace-only must be treated as no custom name (falls through to the
   `Type [Ident]` display), not rendered as a blank/invisible row.
