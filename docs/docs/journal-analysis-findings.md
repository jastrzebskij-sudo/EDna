# Journal Database — Build Log & Initial Findings

First full build of the journal analysis database, from all 1,559 historical journal log files (2017–2026).

## Where the database actually lives

**Correction to the originally planned short-term kludge**: the plan was to park the built `.duckdb` file directly in this claude.ai Project for ad hoc digging. That turned out to be infeasible — the Project's document store has a hard whole-project token budget (~2,000,000 tokens) on top of a per-file cap, and even a single ~20MB compressed chunk of this database exceeds that budget on its own. A binary database this size structurally doesn't fit the Project's doc store, which is sized for text/knowledge documents, not data files.

**Actual home**: the full database lives at `D:\Elite\journal.duckdb` on the user's PC — which is also where `data-architecture.md` said it should live long-term anyway, so this isn't a step backward. It's reachable in any future session via the device bridge (staging it into a session, or eventually via `device_bash` once the current PC file-sharing mount issue clears).

**How it got there**: built in a cloud session (staged all 1,559 source files, parsed with a generic non-branching JSON-Lines parser, wrote to DuckDB), then compressed (xz, 1.73GB → 35MB), split into two ~20MB/16MB parts (both the raw 1.73GB file and the single-file 100MB gzip exceeded delivery limits), delivered to the user via `SendUserFile`, and written to `D:\Elite` via the device bridge.

**Reassembly needed on the user's PC** (one-time): the two parts must be concatenated and decompressed. In `cmd.exe`, from `D:\Elite`:
```
copy /b journal.duckdb.xz.part00+journal.duckdb.xz.part01 journal.duckdb.xz
```
Then decompress the `.xz` (7-Zip's right-click "Extract Here" works if installed; otherwise, with Python available: `python -c "import lzma,shutil; shutil.copyfileobj(lzma.open('journal.duckdb.xz','rb'), open('journal.duckdb','wb'))"`).

**Integrity checksums** (SHA-256), to confirm the reassembly/decompression worked:
- `journal.duckdb.xz` (after concatenation): `a9ec19eace440263ae7821dacb1bff29c6ec9728dcaeff28009247b971db41ee`
- `journal.duckdb` (after decompression, final file): `2085564f2daf6530441731c7c5b71bf0b6ac6fcdb2e89fc9fc07c8f59ad3c1e8`

## Schema (as built)

- `events` — `timestamp`, `event`, `star_system`, `body`, `source_file`, `file_line`, `raw` (full original JSON per event).
- `ingested_files` — `filename`, `file_mtime`, `file_size`, `status` (`closed_complete`/`open_partial`), `ingested_at`.

Note: "open" file detection used the true latest in-game event `timestamp` per file rather than filename sort order — a batch of old `JournalAlpha.*` test-build files from 2021 sorts alphabetically after `Journal.2026-*` (character-wise, "Journal." < "JournalAlpha"), which would have misidentified a 2021 file as the live session. `MAX(timestamp)` per file is the reliable signal, not the filename string.

## Build results

- **2,018,910** total events ingested, **0** parse errors across all 1,559 files.
- **214** distinct event types.
- **1,559** files tracked in `ingested_files` (all expected files present); 1 marked `open_partial` (the true latest — `Journal.2026-07-26T095712.01.log`), 1,558 `closed_complete`.
- Top event types by volume: `ShipTargeted` (408,155), `FSSSignalDiscovered` (238,093), `Music` (196,427), `ReceiveText` (165,593), `UnderAttack` (113,277), `ShipLocker` (86,461), `Cargo` (84,753), `MiningRefined` (63,906), `Scan` (49,080), `Friends` (48,457) — long tail down to `ReservoirReplenished` (11,093) at #25.

## Initial findings on the motivating question (CQC / PowerPlay / Thargoids)

Matches the user's own account of having neglected these activities:

- **PowerPlay: zero engagement.** No `Powerplay*` events anywhere in 10 years of logs.
- **CQC: no evidence of play.** No event type matches `CQC`; every raw-text hit is a false positive — the `CQC` rank/progress field (always 0) inside routine `Rank`/`Progress`/`Statistics` events, plus a couple of incidental chat-text matches. Nothing suggesting actual arena play.
- **Thargoids: passive/incidental contact only, no direct combat evidence found.** 843 raw-text hits, mostly `Materials` (491 — Thargoid-tissue collectible names), `ReceiveText`, `CollectCargo`, `CodexEntry`, `FSSSignalDiscovered`. Only 31 hits for `Interceptor`, all signal detections/codex entries, not combat. `Scout` had a high hit count (28,971) but that's almost certainly dominated by the mundane "Scout" NPC/ship-role term rather than Thargoid Scouts specifically — not disambiguated in this pass.

## Open items

- The `Scout` count needs disambiguation (mundane NPC role vs. Thargoid Scout) if PowerPlay/Thargoid/CQC engagement level becomes a feature question rather than idle curiosity.
- The standalone `etl.py`/`schema.sql`/`requirements.txt` packaging (per `data-architecture.md` §5) still isn't built — this was a one-off script run inside a session, not yet the shareable tool.
- Once the PC's file-sharing mount issue clears, re-verify this database is reachable via `device_bash` directly (would simplify future querying versus re-staging).
