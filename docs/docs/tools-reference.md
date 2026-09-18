# Elite Dangerous Third-Party Tools & API Reference

Research catalogue for designing a custom Claude-based "Ship's Computer" that reads Journal/Status.json and does LLM reasoning/narration on top. Pure reference — no code/design here.

Context: user already runs **EDMC**, **EDCoPilot**, **EDDiscovery**, **ED (Odyssey) Materials Helper**, and uses **Inara** manually.

---

## 1. Journal / Status Data Sources (the raw input)

| Item | What it is | URL | API doc | Notes |
|---|---|---|---|---|
| **Official Player Journal Manual (Frontier)** | Frontier's own spec for the line-delimited JSON journal files (`Journal.<timestamp>.log`) — event names, fields, versioning by game update. Distributed as a PDF, updated per major release (currently up to Odyssey/Horizons-era versions, e.g. v32). | https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf | same PDF | This is the authoritative schema. New/changed events are announced each update in Frontier Forums threads, e.g. [Journal docs for v3.7](https://forums.frontier.co.uk/threads/journal-docs-for-v3-7-fleet-carriers-beta.540745/), [v3.4](https://forums.frontier.co.uk/threads/journal-docs-for-v3-4.508702/), [general v3.0 discussion](https://forums.frontier.co.uk/threads/journal-documentation-for-v3-0.401661/). |
| **Elite Dangerous Journal (community mirror/docs)** | Readable, browsable HTML docs mirroring/annotating the journal spec (community-maintained, easier to navigate than the raw PDF). | https://elite-journal.readthedocs.io/ | n/a (docs site) | Includes the **Status File** page below. |
| **Status File docs** | Documents `Status.json`: full file rewritten every few seconds (not appended like the journal). Fields: timestamp, current event context, `Flags` (32-bit) + `Flags2` (22-bit) bitfields for ship/SRV/on-foot state (docked, supercruise, shields up, landing gear, FA off, low fuel, etc.), pips, fuel, cargo, GuiFocus (which UI panel is open, 12 values), and on-foot extras (O2, health, temperature, gravity, selected weapon) plus lat/long/heading/altitude when landed. | https://elite-journal.readthedocs.io/en/latest/Status%20File.html | same | Best single reference for building a live HUD/status reader; complements journal events for real-time state. |
| **Companion API (CAPI / "Frontier API")** | Frontier's authenticated HTTP API (OAuth) that EDMC/Inara/etc. poll for market, shipyard, outfitting and (recently) fleet-carrier data — separate from the Journal/Status files. Undocumented officially; reverse-engineered by EDCD. | n/a (no official public docs) | Implementation reference: EDMC's `companion.py` in https://github.com/EDCD/EDMarketConnector | Carries extra validation burden (staleness) per EDDN's developer docs. Likely lower priority than Journal/Status for a narration assistant, but relevant if you want live market/shipyard data beyond what journal events emit. |
| Community journal reader libraries | Prebuilt journal tailers in various languages, useful as reference implementations rather than dependencies. | e.g. [EliteJournalReader (C#)](https://github.com/MagicMau/EliteJournalReader), [elite-api (Go)](https://pkg.go.dev/github.com/BenJuan26/elite), [elite (Go, mrdrarek)](https://pkg.go.dev/github.com/mrdrarek/elite-api) | n/a | Good for seeing common parsing patterns (tailing the newest `Journal.*.log`, handling file rollover, watching `Status.json` for changes). |

---

## 2. Data Aggregation Networks (EDDN / EDSM / Inara / Spansh)

### EDDN — Elite Dangerous Data Network
- **What**: A ZeroMQ-based pub/sub relay that lets any tool broadcast journal/CAPI-derived market, shipyard, outfitting, and scan data for other tools to consume. It's the backbone that keeps EDMC, EDSM, EDDB-successors, Spansh, Inara, etc. in sync with each other.
- **URL**: https://github.com/EDCD/EDDN (code), https://eddn.edcd.io/schemas.html (schema list), wiki: https://github.com/EDCD/EDDN/wiki
- **API doc**: https://github.com/EDCD/EDDN/blob/master/docs/Developers.md (publishing/subscribing spec), https://github.com/EDCD/EDDN/blob/master/docs/Contributing.md
- **Publish**: HTTPS POST to `https://eddn.edcd.io:4430/upload/` (note nonstandard port, trailing slash required), UTF-8 JSON body, optional gzip. Only sources: Journal files or CAPI. 413 if payload >~1MiB; 426 if schema version retired.
- **Subscribe**: ZeroMQ `tcp://eddn.edcd.io:9500`, zlib-decompress each message, filter client-side by `$schemaRef`.
- **Auth/rate limits**: none documented beyond required identification headers (`uploaderID`, `softwareName`, `softwareVersion`, `gameversion`, `gamebuild`).
- **Relevance**: Not needed to *read* your own commander's data (you already have the journal locally), but relevant if the Ship's Computer wants to enrich narration with galaxy-wide crowd data (e.g. "this system was scanned by 4 other commanders this week") or if you want to *contribute* data back to the ecosystem. Low priority for a personal assistant, high value if you ever want community-scale context.

### EDSM — Elite Dangerous Star Map
- **What**: Community star-mapping/trip-log database with the most complete public system-position data and a full commander flight-log/trip-tracking API. EDDiscovery and many exploration tools sync to it.
- **URL**: https://www.edsm.net/
- **API docs** (split by resource, all under `edsm.net/en/api-*`):
  - Systems: https://www.edsm.net/en/api-v1 (system lookups, coordinates, bodies)
  - Single system: https://www.edsm.net/en/api-system-v1
  - Logs (commander flight log / visited systems): https://www.edsm.net/en/api-logs-v1
  - Journal ingestion (submit journal events to EDSM): https://www.edsm.net/en/api-journal-v1
  - Commander profile: https://www.edsm.net/en/api-commander-v1
  - Status: https://www.edsm.net/en/api-status-v1
- **Auth**: commander name + personal API key (found in EDSM account settings) for write/commander-specific endpoints; system/body lookups are open, no key.
- **Relevance**: Good source for enriching narration with system metadata (distance from Sol, known bodies, whether already discovered by others) and for cross-referencing your own trip history if EDDiscovery already syncs it there. TypeScript types exist unofficially: https://github.com/kayahr/edsm.

### Inara
- **What**: The community reference site the user already uses manually (trade, engineering, community goals, commander/squadron profiles). Also has a real API for syncing commander data from apps (EDMC has a built-in Inara plugin).
- **URL**: https://inara.cz/
- **API docs**: https://inara.cz/elite/inara-api/ (overview), https://inara.cz/elite/inara-api-docs/ (spec), developer guide: https://inara.cz/elite/inara-api-devguide/, data-exchange format (SLEF): https://inara.cz/elite/inara-impexp-slef/
- **Auth**: `APIkey` header — either a personal key or an app-specific key — plus `appName`/`appVersion`, optional `commanderName`/`commanderFrontierID`.
- **Format**: JSON only, header + `events` array; responses returned in the same order as the request events.
- **Scope**: profile, friends, permits, credits/assets/loans, financial stats, pilot/engineer/power ranks, faction reputation, cargo/materials/inventory CRUD, ship & loadout management (incl. engineering mods), suit loadouts, flight log (FSD jumps, docking, carrier jumps).
- **Rate limits**: none explicitly published; documentation asks for "reasonable timeouts and retry rates" and to back off during maintenance.
- **Relevance**: Could let the Ship's Computer *pull* Inara-side context (e.g. community goal status, best sell prices the user has bookmarked) or *push* structured events the user would otherwise enter into Inara manually — but this overlaps with what EDMC's Inara plugin already automates.

### Spansh
- **What**: Route-plotting and galaxy-data indexing tool — neutron star "highway" plotter, exact/galaxy plotter, trade route optimizer, and a full systems/bodies data dump (spun up partly as an EDDB successor after EDDB went offline).
- **URL**: https://spansh.co.uk/ (plotter UI), https://spansh.co.uk/exact-plotter, project/dev updates via Patreon: https://www.patreon.com/cw/spansh
- **API docs**: no single public developer-docs page found (the plain `/api` path 404s); third-party tools integrate against undocumented/reverse-engineered endpoints — see EDMC plugin example [SpanshRouter](https://forums.frontier.co.uk/threads/edmc-spanshrouter-a-plugin-to-use-the-neutron-highway-in-edmc.518339/) and [Auto_Neutron](https://github.com/Numerlor/Auto_Neutron) for working request examples. Issue tracker: https://github.com/spansh/elite-dangerous-issues.
- **Relevance**: If the assistant wants to narrate/suggest exploration routes, Spansh is the de facto standard; treat its API as "exists but undocumented — read a client implementation to learn the shape."

---

## 3. Existing Companion Tools & Their Extension Points

### EDMC — Elite Dangerous Market Connector
- **What**: The standard journal-watcher/plugin host; almost every other tool either is an EDMC plugin or reads the same journal directory independently.
- **URL**: https://github.com/EDCD/EDMarketConnector · directory entry: https://edcodex.info/?m=tools&entry=150
- **Plugin API doc**: https://github.com/EDCD/EDMarketConnector/blob/main/PLUGINS.md (current), plugin list/registry: https://github.com/EDCD/EDMC-Plugin-Registry, older wiki page (stale): https://github.com/EDCD/EDMarketConnector/wiki/Plugins
- **Mechanism**: Plugins are Python 3.7+ packages with a `load.py` exposing `plugin_start3()`. Key hooks:
  - `journal_entry(cmdr, is_beta, system, station, entry, state)` — fires per journal event, main thread, `entry` is the raw event dict, `state` carries derived commander/ship/cargo/materials/rank info.
  - `dashboard_entry(cmdr, is_beta, entry)` — fires when `Status.json` changes (~1/sec in flight).
  - `cmdr_data(data, is_beta)` / `cmdr_data_legacy()` / `capi_fleetcarrier()` — CAPI market/shipyard/fleet-carrier data (throttled).
  - `plugin_prefs()` / `plugin_app()` — add Tk UI (settings tab, main-window widgets).
  - Threading rules (must not touch Tk off main thread), typed config accessors, `requests`+certifi for HTTP, ships as a zip, semantic-versioned.
- **Relevance**: **Almost certainly the fastest integration path** — write an EDMC plugin that taps `journal_entry`/`dashboard_entry` and forwards events to your Claude-based reasoning layer, reusing EDMC's file-tailing, cross-platform packaging, and existing install base rather than re-implementing a journal watcher.

### EDCoPilot
- **What**: Voice co-pilot with canned + generated narration/chatter, TTS (including Azure Neural / Edge TTS voices), and UI panels; already in the user's toolkit.
- **URL**: https://www.razzafrag.com/ (home/about), wiki: https://razzserver.com/dokuwiki/, directory: https://edcodex.info/?m=tools&entry=533
- **Extension surface**: No formally published third-party plugin/API doc was found, but a real integration exists and is documented from the *other side*: **COVAS:NEXT** (see below) talks to EDCoPilot via message passing — exchanging conversation/speech-coordination messages, forwarding commander messages and COVAS:NEXT's replies into EDCoPilot, negotiating which app's TTS speaks, sending a summary of visible EDCoPilot panels, and optionally driving EDCoPilot's UI. Doc: https://ratherrude.github.io/Elite-Dangerous-AI-Integration/50_EDCoPilot/. EDCoPilot also supports user-authored custom chatter/event scripts (text files defining custom voice lines triggered by conditions) — this is the "canned narration" surface already used by CMDRs, distinct from the programmatic COVAS integration.
- **Relevance**: Rather than building your own TTS/voice pipeline from scratch, the COVAS:NEXT integration shows a proven pattern for piping an LLM's narration *into* EDCoPilot's existing speech queue/UI — worth evaluating as an alternative to building narration output yourself.

### COVAS:NEXT (formerly "AI Integration: Ship Computer") — directly relevant prior art
- **What**: An existing open-source **LLM-powered voice copilot for Elite Dangerous** — essentially the same category of project the user is designing. Reads the journal file (reacts to "every event"), supports OpenAI, OpenRouter, or local LLMs as the backend, does speech-to-text (Whisper) and TTS, supports function-calling (fire weapons, adjust speed, etc.), can take screenshots for vision analysis, and calls out to EDSM for system data/Galnet news.
- **URL**: https://github.com/RatherRude/Elite-Dangerous-AI-Integration · docs: https://ratherrude.github.io/Elite-Dangerous-AI-Integration/ · overview: https://ratherrude.github.io/Elite-Dangerous-AI-Integration/30_description/ · directory: https://edcodex.info/?entry=599&m=tools · Frontier forum thread: https://forums.frontier.co.uk/threads/covas-next-ai-ship-integration.627910/
- **Relevance**: Worth reading closely as architectural prior art (journal-tailing pattern, function-calling design, EDCoPilot bridge) even if the user builds something bespoke around Claude instead — it's the closest existing analog to "Ship's Computer."

### EDDiscovery
- **What**: "Captain's log and 3D star map" — trip/exploration tracking, journal history browser, 3D galaxy visualization; already in the user's toolkit.
- **URL**: https://github.com/EDDiscovery/EDDiscovery · wiki: https://github.com/EDDiscovery/EDDiscovery/wiki · org: https://github.com/EDDiscovery · directory: https://edcodex.info/?m=tools&entry=10
- **Extension surface**: C#/.NET desktop app; no documented third-party plugin API found in this pass. It reads local journal files directly and syncs exploration data to EDSM.
- **Relevance**: Primarily useful as a *data source pattern* (it already parses full journal history into a local DB) rather than something to extend — if a historical/queryable store is wanted, its local DB or EDSM sync could be a reference or reuse target.

### ED (Odyssey) Materials Helper
- **What**: Cross-platform (Java/JavaFX) engineering-materials tracker — tracks raw/manufactured/encoded materials, blueprints, engineering requirements; already in the user's toolkit.
- **URL**: https://github.com/jixxed/ed-odyssey-materials-helper · README: https://github.com/jixxed/ed-odyssey-materials-helper/blob/master/README.MD · directory: https://edcodex.info/?m=tools&entry=582
- **Extension surface**: No documented plugin API found; reads the journal directly. Open source, so its material/blueprint-requirement data tables could be read/reused as a reference dataset (e.g. "what materials does blueprint X need") rather than integrated live.
- **Relevance**: If the assistant wants to narrate engineering progress ("you need 3 more Proto Light Alloys for this mod"), this repo's bundled data is a candidate reference source rather than an API to call.

---

## 4. Development Guides & Communities

| Resource | What it is | URL |
|---|---|---|
| **EDCD (Elite Dangerous Community Developers)** | The umbrella GitHub org behind EDMC, EDDN, the plugin registry, and EDDI — the de facto center of gravity for third-party ED tool development. | https://github.com/EDCD |
| **EDMC Plugin Registry** | Curated, maintained list of working EDMC plugins (supersedes the stale wiki list). | https://github.com/EDCD/EDMC-Plugin-Registry |
| **EDCD/EDDI** | Another major open-source "AI companion" project (speech, TARGET/VoiceAttack integration) predating COVAS:NEXT — worth a skim for its journal-event-to-speech architecture. | https://github.com/EDCD/EDDI |
| **Frontier Forums — "Elite API and Tools" subforum** | Official forum section where Frontier and the community discuss journal doc releases, EDDN, EDSM, EDMC, etc. First place to check for schema changes after a game update. | https://forums.frontier.co.uk/forums/elite-api-and-tools/ |
| **EDCodex** | Community-run directory ("steroids version" of the old master-list Reddit thread) cataloguing tools, videos, and wikis by category (mining/trading, exploration, BGS/squadrons, ship/loadout, graphics, voice/audio, companion apps, data/databases). Good first stop when scouting for any tool by category. | https://edcodex.info/ (tools index: https://edcodex.info/?m=tools) |
| **ed.tools** | A guides/news hub (YouTube-guide aggregator + a few utility pages) — less relevant for API/dev research than EDCodex/EDCD, more useful for gameplay guides. | https://ed.tools/guides |
| **elite-journal.readthedocs.io** | Community-maintained readable mirror of the Journal + Status File docs (see §1). | https://elite-journal.readthedocs.io/ |

---

## 5. Other Notable Tools (brief)

| Tool | One-liner | URL | Plugin/API? |
|---|---|---|---|
| **Coriolis (EDCD Edition)** | Web-based ship-builder/loadout planner; the long-standing standard for sharing ship builds. | https://github.com/EDCD/EDMarketConnector (EDCD org) / directory: https://edcodex.info/?m=tools&entry=142 | Ships as an EDMC plugin (export current ship to Coriolis); build-import URLs are a de facto interchange format. |
| **EDSY** | Alternative ship-builder/loadout planner to Coriolis. | directory: https://edcodex.info/?m=tools&entry=484 | Build URL import/export, no broader API found. |
| **BGS-Tally** | EDMC plugin tracking Background Simulation, Colonisation, Powerplay, and Thargoid War activity per faction/system. | https://github.com/aussig/BGS-Tally | EDMC plugin (good second example of the plugin pattern beyond EDDN/EDSM/Inara). |
| **Elite Observatory / ObservatoryCore** | Extensible standalone tool for processing Elite Dangerous journals, notably strong at exploration/scan value-of-interest alerts. | https://github.com/Xjph/ObservatoryCore | Has its own plugin system for journal processing — another architecture reference. |
| **EliteVA** | Bridges EDMC/journal events into VoiceAttack for voice-command profiles. | directory: https://edcodex.info/?m=tools&entry=612 | EDMC plugin + VoiceAttack plugin bridge. |
| **VoiceAttack** | General-purpose voice-command macro tool widely used with ED via community profiles (e.g. HCS Voicepacks) and TARGET scripting for status.json-driven controls. | directory: https://edcodex.info/?m=tools&entry=295 | Its own scripting/plugin ecosystem; relevant if voice *input* (commands) is ever added alongside narration output. |
| **Elite Intel** | Overlay/intel tool surfacing CMDR/system threat info from journal + community data. | directory: https://edcodex.info/?m=tools&entry=615 | n/a found. |
| **EDDB (legacy) / successors** | The original crowd-sourced systems/stations/commodities database; officially offline, functionally superseded by Spansh's data dumps and EDSM. | directory: https://edcodex.info/?m=tools&entry=53 | Historical reference only. |
| **Trade Dangerous** | Long-running command-line trade-route optimizer, one of the oldest ED third-party tools. | directory: https://edcodex.info/?m=tools&entry=12 | CLI + its own local DB; no hosted API. |
| **EDDI** | See §4 — speech/event-driven companion predating COVAS:NEXT, still active. | https://github.com/EDCD/EDDI | Own plugin/personality system. |
| **o7 Debrief, EliteMining, EDLD, Elite Dangerous Dashboard, EDU (Unified App), ED Mission Operator, ED Colonisation Assistant, Carrier Traversal System, Artemis Scanner Tracker, EDXD, EDMRN, Exploration Buddy, Neutron Dancer, Explorer Lite, OD Explorer, EDSMT, ED Ship eXporter, Elite Dangerous Orrery, EDHM, ED3D Galaxy Map, EDFX, EDSpec (Discord bot)** | Long tail of narrower single-purpose tools (mining assistants, cargo logs, carrier jump trackers, HUD/graphics mods, Discord bots, etc.) catalogued on EDCodex — scan by category if a specific niche (e.g. mining, carriers, colonisation) becomes relevant. | full index: https://edcodex.info/?m=tools | Varies; most either read the journal directly or ship as EDMC plugins. |

---

## Bottom-line takeaways for brainstorming

1. **Journal + Status.json are fully documented** by Frontier (PDF manual) and mirrored more readably at elite-journal.readthedocs.io — no reverse-engineering needed for the core input.
2. **Writing this as an EDMC plugin** is the path of least resistance for ingestion (Python, well-documented hooks, reuses the user's existing install) rather than writing a standalone file-tailer.
3. **COVAS:NEXT and EDDI are direct prior art** for an LLM-driven ship computer — both worth reading as architecture references, and COVAS:NEXT's EDCoPilot bridge is a ready-made pattern for piping narration into the user's existing EDCoPilot TTS/UI instead of building new voice output.
4. **EDDN/EDSM/Inara/Spansh** are optional enrichment layers (galaxy-wide context, route planning, community data) rather than required for a personal narration assistant — evaluate opportunistically, not as day-one dependencies.
5. **EDDiscovery and ED Materials Helper** don't appear to expose third-party APIs/plugin systems in current docs — treat them as parallel, independent journal consumers (possible data-format/reuse references) rather than integration targets.
