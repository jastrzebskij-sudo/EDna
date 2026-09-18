# Journal Data Architecture

Consolidates four rounds of design research (informational/analytical only — see `design-principles.md`; nothing here reads live game state to act on the player's behalf, it's historical log analysis). Source data: 1,559 journal log files on the user's PC, JSON-Lines format, ~1.18GB, spanning 2017–2026.

## 1. Storage & access

- **The database lives as a plain local file, not a server.** SQLite/DuckDB are embedded engines — "opening the file" is "connecting." No daemon, no persistent process, because none of this project's environments can durably host one: Claude's cloud execution is session-only and ephemeral, and the user's PC is reachable only through the device bridge (file staging + remote shell), not as a network-addressable host.
- **A "container as a web resource" is not durably achievable here** — worth stating plainly rather than half-designing around it. Two independent walls: no stable public URL for Claude's own execution environment, and even if one existed, a published Artifact's JS can't reach any custom host anyway (its CSP allows script tags only from a small CDN allowlist plus Google Fonts stylesheets; every other outbound fetch is silently blocked).
- **If/when a web-page tool (Artifact) is built on top of this data**, the only two legitimate paths are: (a) a static/precomputed snapshot baked in at publish time, or (b) curated aggregate views pre-loaded into the artifact's own platform-hosted database capability, which the live page can then query/filter — genuinely interactive, but sized for curated summaries, not a mirror of the full dataset. No custom API/server path exists; don't design toward one.
- **Engine choice: DuckDB over SQLite** for the analysis layer — columnar/vectorized, built for exactly this shape of workload (aggregations, group-bys, time-series over years of play), reads JSON-Lines natively (doubles as the ETL tool), still a single embedded file. SQLite only if some downstream tool specifically requires it; DuckDB can export/attach to SQLite later if needed, so this isn't a one-way door.

## 2. ETL design (historical backfill)

- **Schema: hybrid.** An `events` table with a few extracted/indexed columns (`timestamp`, `event`, `star_system`, `body`, `source_file`, `file_line`) plus a native DuckDB `JSON` column holding the complete raw event object. Optional derived/materialized tables for heavily-queried event types (docking, market transactions, exploration scans), built as `CREATE TABLE ... AS SELECT ...` on top of `events` — additive, cheap to rebuild, not the primary store.
- **Idempotency**: an `ingested_files` metadata table (filename, mtime, size, status, last_line_ingested) so re-runs only touch new/changed files, never reprocess the full corpus.
- **Messy data handling**: parse line-by-line, skip unparseable trailing lines (from a file caught mid-write) rather than failing the whole file; the lexicographically-newest filename is treated as the open/live session file and given `status = open_partial`, everything else `closed_complete`.
- **Where it runs**: locally on the user's PC via the device bridge (Claude invoking a local script), not by staging 1.18GB into Claude's cloud container — the data and the destination DB both already live on the same machine; staging it elsewhere just to write results back there is pure overhead.

## 3. Ongoing ingestion (new sessions going forward)

- **Live-tailing isn't something Claude can implement or operate** — it requires a process resident and watching the file continuously while the game runs, independent of whether any Claude session is even open. That's the same category of thing EDMC/EDDI already are; Claude has no mechanism to sit in a loop between invocations.
- **Recommended: lazy session-start consolidation, not live-tail and not a standalone daemon.** The incremental-mode ETL script runs automatically as a first step whenever a Claude session next works with this project — "catch up on anything new right before answering." No freshness need justifies more than this: the assistant is consulted between/after play, not queried live mid-flight (EDMC/EDDI already own real-time in-game telemetry; duplicating that here is pure redundancy).
- **Future option, not needed for v1**: if true real-time ever becomes valuable, EDMC exposes a plugin API (`journal_entry()` callback) — a thin plugin reusing EDMC's live-tail/reconnect logic beats building a redundant file watcher from scratch.

## 4. Schema evolution resilience

Frontier ships regular game updates; new event types and new fields on existing events will keep appearing. The hybrid schema absorbs this by construction:

- **New fields on existing event types** — silently absorbed by the raw-JSON column; older rows just return `NULL` for a field they predate. No reprocessing.
- **Brand-new event types** — silently absorbed by the generic `events` table, *provided the ETL's insert logic stays generic* (parse → extract known top-level keys if present → insert raw JSON) rather than branching per event type. No code change needed the first time one appears.
- **Indexes are cheap and decoupled from source files.** DuckDB's `CREATE INDEX` (ART-based) operates only on data already in the `.duckdb` file — it never reopens the original journal logs. Adding an index later, or extracting a previously-unindexed JSON field into a real column, is a single-pass operation over existing rows (seconds–minutes), never a re-ETL. DuckDB's automatic zonemaps (per-row-group min/max stats) also cover a lot of range/filter query speed without any explicit index.
- **Defensive practice to build in**: log any event type not seen before (visibility into "this update added N new events") without gating ingestion on it.
- **The only manual step, ever**: promoting a newly-interesting event type into a derived table — a query over data already in the DB, not a reprocessing job.

## 5. Replicability as a standalone tool

Confirmed: nothing about this design requires AI at runtime. The architecture reasoning (this doc, and the conversation behind it) is a one-time authoring cost; what ships is pure code.

- **ETL/parsing**: pure Python + DuckDB. No LLM call anywhere in the path.
- **Future schema drift, for any user**: handled entirely by the static generic-insert logic already in the script — Frontier shipping a new event type doesn't trigger any AI involvement for anyone running the tool.
- **Minimal standalone distributable**: `etl.py` (CLI, takes a journal folder path, does parse/insert/idempotency/unknown-event-logging), `schema.sql` (or inline DDL), `requirements.txt` (essentially just `duckdb`). Clone, `pip install`, run one command, get a queryable `.duckdb` file — no API keys, no network calls, no AI step in anyone else's usage.
- This is a strong future candidate for `engineering-practices.md`'s "package proven capabilities" principle — build it once here, validate it against the real 10-year corpus, then it's a clean, shareable artifact for other players.

## 6. Short-term plan (adopted, then corrected on build)

Original intent was a deliberate kludge: build the database once and store the resulting `.duckdb` file directly in this claude.ai Project, for ad hoc digging across future sessions without redoing device-bridge staging each time.

**That specific placement turned out to be infeasible and was corrected during the first build**: the Project's document store has a hard whole-project token budget (~2,000,000 tokens) in addition to a per-file cap, and even a single ~20MB compressed chunk of the built database (1.73GB raw, 35MB xz-compressed) exceeds that budget by itself. A binary database of this size structurally doesn't fit a doc-oriented knowledge store.

**What actually happened instead**: the built database lives at `D:\Elite\journal.duckdb` on the user's PC — which is also its long-term home per section 1 above, so this isn't a step away from the target architecture, just arriving at it sooner than planned. It was delivered there via `SendUserFile` (split into two compressed parts to fit delivery size limits) + the device bridge's `device_commit_files`, with one manual reassembly step on the user's end (see `journal-analysis-findings.md` for the exact commands and checksums). The Project instead holds a proper text doc (`journal-analysis-findings.md`) with the build log, schema, row counts, and initial findings — which is exactly the kind of thing the Project's doc store is for.

**Still true and still the near-term shortcut**: this was a one-off script run inside a session (staging + a Python/DuckDB ETL), not yet the standalone, packaged `etl.py`/`schema.sql`/`requirements.txt` tool from section 5. Revisit and formalize that once the exploratory pass shows which views/questions actually matter.

## Open items

- The standalone `etl.py` / `schema.sql` / `requirements.txt` tool isn't written yet — this doc is the design, not the implementation; the first real build was a one-off session script.
- Which event types deserve promotion to derived/materialized tables isn't decided — depends on what the exploratory pass in `D:\Elite\journal.duckdb` turns up.
- `CQC` confirmed to show no evidence of actual play in the built database (only false-positive rank-field matches) — see `journal-analysis-findings.md`. The `Scout` event-count disambiguation (mundane NPC role vs. Thargoid Scout) remains open if this becomes a feature question later.
- Once the PC's current file-sharing mount issue (a known Windows-update regression affecting `device_bash` access to connected folders, as of this session) clears, re-verify the database is reachable via direct shell rather than re-staging each time.
