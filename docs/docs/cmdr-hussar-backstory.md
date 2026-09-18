# CMDR James Hussar — Backstory & Motivational Profile

Assembled from three sources, kept clearly separated below: (1) the journal database (`journal.duckdb`, hard behavioral evidence), (2) the public Inara profile at `inara.cz/cmdr/13238` (self-authored facts the player wrote themselves, at various points over the years), and (3) connective narrative — my own synthesis linking 1 and 2 into a coherent backstory, offered as a *reading* of the character, not a claim of documented fact. The tags `[data]`, `[inara]`, and `[synthesis]` mark which is which throughout, so this stays a usable tool rather than something to take too literally.

Assembled at the user's request, following the persona-dialogue round in `journal-visualization-tool.md`, specifically to store away and inform future in-game goals — not just a one-off writeup.

**Revision note (this round):** the original version of this document got the squadron's home-turf history backwards, treating Inara's current "Home System: Rigel" field as if it had always been true. The user corrected this directly: *"Historically Ghost Legion is based out of Phiagre, a system my character was based out of and frequented for years. Only since the Colonization update did the squadron relocate."* A fresh query independently confirms the correction, strongly — see below — and also caught a false-positive in the original doc's own Rigel claim, which is corrected too.

## Identity

- **Commander James Hussar** `[data]` — from the journal's own `Commander` event; the account/journal history runs from **14 May 2017** to **27 July 2026**, ~6,997 hours across 1,559 sessions.
- **Squadron: Ghost Legion [GHST]** `[inara]` — Inara currently lists home system **Rigel**, 215 members (187 in-game, 25 active in the last 7 days). Motto: *"The price of peace is eternal vigilance."* Three explicit principles: no piracy, no griefing, no cheating. No mandatory events or schedule — a squadron built around flexibility, not attendance. **Historically based out of Phiagre** `[user-stated, corroborated below]`, relocating to Rigel only since the Colonisation/Trailblazers update (~Feb 2025).
- **Squadron's associated minor factions**: **The Sovereign Justice Collective** and **Nahuaru Crimson Bridge Int** `[inara]`.
- **Allegiance: Independent. Power: Independent.** `[inara]` — confirmed by data: zero `Powerplay*` events anywhere in nine years `[data]`. Never pledged, not an oversight — a genuinely consistent nine-year position.
- **Self-described play style: "Relaxed/casual, Any mode,"** availability "Occasionally." `[inara]` — worth noting against 6,997 real hours; "relaxed" reads as *unscheduled and unpressured*, not *casual in volume*.
- **Overall rank: Elite V.** `[inara]` A long-tenure veteran rank, consistent with career length.
- **Registered ship shown on profile: Quo Vadis** (Mandalay, JA-14M) `[inara]` — the fleet's actual long-range distance leader, 111,400+ ly logged `[data]`. Current loadout (last `Loadout` event, 2 June 2026): **77.2 ly max jump range**, 32t main fuel tank `[data]`.
- **Fleet carrier: Spacial Circumstances** (J6H-95L) `[inara]`, lightly used relative to fleet size — 33 real carrier jumps against a 32-ship fleet `[data]`.
- **Current home: Col 132 Sector WC-X c16-7** `[inara]` — the last (sixth) of six systems personally claimed via `ColonisationSystemClaim` between **3 Oct 2025 and 9 Jan 2026** `[data]`: Shui Wei Sector FW-W d1-95 → Col 285 Sector DZ-J b24-0 → Col 285 Sector OX-B b13-1 → Col 140 Sector IH-V d2-6 → Col 132 Sector VF-N d7-64 → Col 132 Sector WC-X c16-7. The Inara profile's location field and the journal's colonisation data agree with each other: this isn't a passing outpost, it's the literal, current answer to "where do you live."
- **Inara supporter badge** `[inara]` — consistent with this project's existing note (`inara-api-notes.md`) that the user has financially supported Inara's developer directly.

## Phiagre: the real historical home, confirmed independently

The user's correction is well-supported by the journal's own hard data — more strongly, in fact, than the original (incorrect) Rigel framing ever was:

- **20,265 total raw mentions of Phiagre** across all event types, and **3,653 direct `FSDJump`/`Docked`/`Location` events there specifically** `[data]`.
- Those visits span **2017-05-14 through 2025-12-14** `[data]` — essentially the entire pre-Colonisation career.
- **The very first `StartJump`/`FSDJump` in the entire nine-year journal (2017-05-14, 02:39:10–02:39:28) is a jump into Phiagre** `[data]`. This commander's career didn't just pass through Phiagre — it *began* there.
- **The very first `Docked` event in the whole journal (2017-05-14, 02:43:02, at "The Victoria Chappell Foundation") shows `"StationFaction": "The Sovereign Justice Collective"` in the raw event data** `[data]` — the squadron's own associated faction, controlling the very first station this commander ever docked at.
- The last recorded Phiagre visit is 2025-12-14 `[data]` — right around when the colony-claiming spree (starting 2025-10-03) was already underway, consistent with a home base being wound down as a new one was being built.

`[synthesis]` This reframes the "justice connection" finding from the previous round (below) in a much better light: it isn't a story about a contractor who never visited HQ. It's the opposite — the entire nine-year bounty-hunting career for the Sovereign Justice Collective was run out of, and anchored at, the very system where that relationship began on day one.

## Rigel: a second correction — zero visits, not one

The original version of this document claimed "a single `FSDJump` into a system matching 'Rigel,' zero dockings." Re-checking that claim against the raw matched rows (per this project's standing verification habit) found it was **itself a false positive**: every "Rigel" match in the journal — one `FSDTarget`, `StartJump`, `FSDJump`, `ReceiveText`, and `FSSDiscoveryScan`, all from the same jump on 2025-12-16 — turns out to be the system **"Maidubrigel,"** which merely contains "rigel" as a substring `[data]`.

The corrected fact is stronger, not weaker, for the future-goals angle below: **CMDR Hussar has never, not even once, visited actual Rigel** — the system that is now, since the relocation, Ghost Legion's own home turf `[data]`. Nine years and 6,997 hours, and the squadron's current front door remains completely unvisited.

For scale: the current home (Col 132 Sector WC-X c16-7) sits roughly **862 ly from Rigel** and **1,198 ly from Phiagre** in a straight line `[data + external]`; Quo Vadis's 77.2 ly jump range would cover either in the rough neighborhood of a dozen or so jumps, depending on the actual route.

## The justice connection — verified, not assumed

The squadron profile names **The Sovereign Justice Collective** as an associated faction; the journal's own bounty-hunting history independently confirms this isn't just a listed affiliation. Across 2,531 `FactionKillBond` awards in nine years, **1,762 — 69.6% of every bounty kill logged — were credited to The Sovereign Justice Collective**, over 14 times the next-largest faction `[data]`. Combined with the Phiagre origin above — first jump, first dock, same faction — this reads as a single continuous thread rather than a coincidence of overlapping names: **a nine-year career built at, and in service of, one specific place and its faction**, from the very first minute of the journal. `[synthesis]`

## Origins — the explorer years

Two self-written logbook entries on Inara sketch an earlier chapter, before the current journal history even begins:

- **19 Aug 2016 — "Jacques Recon and Resupply, Day 47."** `[inara]` A Distant Worlds-style pilgrimage: 47 days, limited jump range, arriving at Jacques Station — "the single most distant human settlement in known history" — at 80 DD-D 774-CE-2. Contributed meta-alloys to the station's supply effort, earned exploration promotions (Ranger, then Pioneer) by turning in 47 million credits of discovery data, then refitted for local mining. Notably: encountered and described giant, ancient jellyfish-like organisms living in gas giant atmospheres nearby — genuine scientific curiosity recorded alongside the practical logistics.
- **26 Dec 2018 — a later entry describing an exploration run to the Witchhead Nebula in an Asp Explorer.** `[inara]` Witchhead sits near Rigel — the system that, at the time, had nothing to do with Ghost Legion (still based at Phiagre) and would only become relevant to the squadron nearly a decade later, after the relocation. `[synthesis: this is a genuine coincidence of geography, not foreshadowing — worth noting precisely because it's NOT the significant thread it might first appear to be, now that Phiagre is understood as the actual historical anchor]`

Both entries predate the journal database's own earliest recorded event (14 May 2017, itself the Phiagre arrival above) `[data]` — this is an earlier phase of the character's history that the hard data doesn't reach, told only in the player's own words at the time. `[synthesis: worth being upfront that these two chapters — data and self-written lore — don't overlap in time; they're adjacent, not cross-verified against each other]`

## A working theory of the arc

`[synthesis — offered as a reading, not a fact]` Wanderer first: a young commander who spent 47 days reaching the edge of known space just to see it, and found something genuinely strange in a gas giant's clouds while there. Home-builder next: nine years anchored at Phiagre, docked first at a Sovereign Justice Collective station and never really leaving that faction's orbit — quiet, out-of-sight bounty work funding a squadron whose motto is about vigilance, not glory. Builder again, but bigger, now: since October 2025, six systems personally claimed and settled, the old home wound down just as the new one took shape. The 2026 session data backs the "builder now" phase directly: colonisation activity is up roughly 6x year over year, and the two most recent sessions (25–26 July 2026) were spent almost entirely hauling construction materials, not exploring or fighting `[data]`.

If that arc is roughly right, the throughline isn't any one activity — it's **staying loyal to a place and the people/faction tied to it, then rebuilding that loyalty somewhere new when circumstances force a move**: a 47-day solo crossing early on, nine years anchored at one system for one faction, and now a fresh six-system colony chain built in the wake of losing the old home. The fleet's own naming style backs this up in a lighter register — witty, understated ship names (*Master of None*, *CarrieAnn De Cargaux*, *High Gravitas Warning*, *Worth The Weight*) suggest someone who doesn't take the grandeur of any of this too seriously, even while doing all of it for real `[inara]`.

## What this suggests for future goals

See `claude/future-aspirations.md` for the full curated list (this section is kept short and points there rather than duplicating it). In short, tied to this backstory specifically:

- **Making the trip to Rigel is now the obvious next chapter, not a "closing an old loop" errand.** The squadron relocated there and the commander has never been — the visit is about *arriving somewhere new the squadron now calls home*, not revisiting anywhere.
- **The colony project (Phiagre's successor, in a sense) has an obvious next chapter of its own**: six systems claimed is a real body of work, not a side activity — worth deciding deliberately whether there's a shape to it, the same way Phiagre had one organically over nine years.
- **Operations (live since June 30, 2026)** remains a natural fit for the justice-and-vigilance identity that ran through the entire Phiagre era, and pairs naturally with a Rigel trip if the squadron is actually active there now.
- **Powerplay remains a genuine non-issue, not a gap to fill for its own sake** — nine years of a clean Independent stance is itself a consistent identity choice, unaffected by the home-system move.

## Sourcing notes / caveats

- Inara profile fetched from `https://inara.cz/elite/cmdr/13238` (the bare `/cmdr/13238` path redirected to the site's general homepage rather than the profile — noted here in case this is revisited later).
- The 2016/2018 logbook entries are the player's own words, quoted/paraphrased from what Inara returned — not verified against the journal, which doesn't cover that period.
- Rigel's galactic coordinates (used for the ~862/1,198 ly distance estimates) came from EDSM (`edsm.net`), an external community star-map site, since the journal itself has no recorded visit to draw coordinates from.
- Everything under "Origins" and "A working theory of the arc" is explicitly interpretive. It's useful as a way to hold the data together and suggest direction, not as a documented biography — worth treating it the same way in any future conversation that builds on it.
- This revision is a good concrete example of the project's own verification habit catching a real mistake after the fact, not just hypothetically: the original "one Rigel jump" claim went unverified at the time it was written and turned out to be wrong (a substring false-positive), caught only when re-examined for this correction.
