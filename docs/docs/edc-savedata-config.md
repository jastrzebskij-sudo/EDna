# EDCoPilot SaveData File — Configurable Keys Reference

For the future "Ship's Computer companion" NPC-voice/config tool. Captures what's actually editable vs. what's just tracked telemetry, in EDCoPilot's per-commander live save-state file, so we don't re-derive this later.

## File location & handling notes

- Path: `C:\EDCoPilot\working\EDCoPilot.SaveData.<COMMANDER_NAME>.LIVE.txt`
  (James's: `EDCoPilot.SaveData.JAMES_HUSSAR.LIVE.txt`)
- A `.LEGACY.txt` backup copy and a plain (non-LIVE) snapshot also exist alongside it.
- **This is EDCoPilot's live, actively-written session database — not a small dedicated config file.** ~11.8MB, flat `Key="value"` / `Category:Key="value"` lines, one per line, 284 distinct key-prefixes, mixing genuine user settings with a huge amount of auto-tracked gameplay history.
- Any tool we build must do a **surgical read → find matching line(s) → replace → write** — never rewrite the whole file — and should be defensive about EDCoPilot possibly writing to it concurrently while running.

## Confirmed format: NPC/crew voice assignment

```
Character:<Role Name or bare NPC Name>="<Provider>|<VoiceID>|<Locale>|<pitch/param>|<optional custom hail .wav>"
```

Example (James's fleet carrier captain, already configured):
```
Character:Captain Chi Velez="Edge|es-DO-EmilioNeural|US|0.0|"
```

Currently only 4 `Character:` lines exist total in his file — his carrier's other 5 crew (Herschel Thompson, Isaac Montgomery, Randall Hill, Sylvester Vinson, Shelton Castaneda) have no line yet (nothing to edit, just new lines to add). Two of the four existing entries (`ALOYSIUS BLACK`, `RICK RAZZAFRAG`) look like EDCoPilot's own built-in example/easter-egg characters, not user-created.

Key naming: for carrier crew it's `"<Role> <Name>"` (matches the `CarrierCrewRoster` line elsewhere in the file); for general NPCs it may just be the bare name in caps. Worth confirming with more real-world examples before finalizing matching logic in the tool.

## Other genuinely user-configurable categories found

| Prefix | Format | What it is | Priority for our tool |
|---|---|---|---|
| `Character:` | see above | NPC/crew TTS voice assignment | **v1 — primary target** |
| `shipNamePronounciation:` | `shipNamePronounciation:<Your Ship Name>="<Phonetic Spelling>"` | Custom pronunciation override for your own (often punny) ship names, e.g. `"The Sploraconda"="The Splorer Conda"` | **v1 — same UI shape/code path as Character:, bundle together** |
| `ExcludeDisplay:` | `ExcludeDisplay:<NPC/Ship Type>="1"` | Suppression list — ship/NPC categories excluded from chatter/display (e.g. `ALLIANCE ENFORCER`, `CRUISE SHIP`) | **v1 — simple toggle-list, same file/pattern** |
| `LocationNote:` | `LocationNote:<mode>:<system>|<body>|<coords>="<note text>"` | User-authored notes pinned to specific coordinates (e.g. Thargoid Spire site callouts) | **v2 — different UI shape (spatial/coordinate-aware), not just a name+value list** |
| `Bookmark:` / `BookmarkGroup:` | `Bookmark:<System>="<System>|<flag>||<Group>"` | Saved systems & bookmark-group organization | **Low priority — EDCoPilot already has a GUI panel for this (Places tab)** |

## Explicitly NOT settings — leave alone

The overwhelming majority of the file (284 total key-prefixes) is auto-tracked session/gameplay history, not configuration. Do not build editors for these; editing risks corrupting real accumulated game data for no benefit:

`Planetary` (40,510 lines — scanned-body cache), `FleetCarrier` (10,488 — carrier *sightings* across the galaxy, NOT your own carrier's config), `LastHere`, `BodyList`, `Faction`/`FactionData`, `LastDocked`, `StationFact`, `Hotspot`/`HotspotPrev`, `Biologicals`/`ScannedSpecies`/`SpeciesDictAdd`, `StoredModule`, `Map`, `FirstFootFall`, `SystemVisited`, `MsgList`, all kill-count categories (`AllKillsByType`, `OnFootKillTotals`, `SRVKillTotals`, `ShipKillTotals`), `Geologicals`, `Weapon`, `ShipSubtotal`, `POI`, `Engineer`, `ShipStats`/`ShipSpecs`/`ShipID`, `Suit`/`SuitLoadout`, `LastWingMessage`, `Mined`, `Rank`, `permit[...]`, `flags`/`flags2`, `RefreshReminder*` (internal version flags), `BGS*` (background-sim tick tracking).

## Suggested v1 scope for the NPC/voice config tool

Given the above, "Speech & Chatter Customization" — `Character:`, `shipNamePronounciation:`, `ExcludeDisplay:` — forms a natural, low-risk v1 scope: same file, same safe-edit code path, all genuinely about voice/display customization rather than gameplay data. `LocationNote:` is a reasonable v2 given it needs a different (spatial) UI. Bookmarks are lowest priority since EDCoPilot already covers them natively.
