# Inara API — Research Notes

Homework pass on `inara-api/`, `inara-api-devguide/`, `inara-api-docs/`, and a search for any public source repo. Context worth keeping in view: Inara is a genuinely community-appreciated resource, its developer (Artie) has been financially supported by the user directly in the past, and any integration here should be pursued respectfully — not silently built against, and not treated as a free resource to extract from without acknowledgment.

## What the API actually is

- Single JSON endpoint (`https://inara.cz/inapi/v1/`), POST-only, header block (app identity + API key + optional commander name/Frontier ID) plus a batched events array.
- **It's write-focused, for commander-data synchronization** — ~60+ event types covering profile, credits/assets/loans, ranks (pilot/engineer/power), faction reputation, cargo/materials/ship-locker inventory, fleet/loadout management, suit loadouts, and flight log (jumps, dockings, carrier jumps).
- **Important correction to `ship-build-advisor.md`'s assumption**: there are **no read-only endpoints for market data, station outfitting, or commodity pricing**. The "Nearest outfitting" search on the website (with its discount filter) is a web-UI feature backed by Inara's internal database — not something exposed through the public developer API. Querying it programmatically isn't an option as currently documented; scraping the web page would violate the site's own stated etiquette (see below) and isn't something to do regardless.
- **Permits: confirmed not available.** The API docs themselves say the permit system "is not implemented on Inara yet (will be available fairly soon)." This resolves the open question in `ship-build-advisor.md` — Inara isn't a fallback source for permit status either, at least not yet.

## Access process — this matters for how we'd approach it

- A **personal API key** (from a user's own account) works for most write events. A separate **application key** exists for read-only events only.
- Getting whitelisted requires **contacting Artie directly** — app name, description, and intended use, before deployment. This isn't a self-serve signup; it's a conversation.
- Explicitly stated etiquette: "be polite!" — no spamming events one-by-one (batch them), no mass scraping, no unauthorized surveillance of other players, cache client-side, send only Live game data (never beta/Legacy), only new/non-duplicate events, timestamps within 30 days. Abuse or high error rates get a key revoked.

## On open-sourcing

Searched specifically for a public repo for Inara's own backend/frontend — found none. Unlike EDMC/EDDN/Coriolis (all on EDCD's GitHub), **Inara itself appears to be closed-source**; the GitHub hits that surfaced are unofficial third-party clients, not Artie's own code. He funds development via Patreon. This is a different situation from every other tool in `tools-reference.md` — there's no code to read here, only the documented API surface.

## Recommendation on approach

Given both the whitelisting process (a direct conversation is required regardless) and the user's existing relationship with Artie, the right move if this ever gets built is to **reach out directly and describe the project honestly before writing any integration code against the API** — not build first and request a key as a formality afterward. Worth being upfront that this is a personal/hobby project, not a commercial one, and worth asking rather than assuming about anything not covered in the docs (e.g., whether there's any appetite for exposing outfitting/discount data via the API in the future, given it's clearly tracked internally already).

## From the dedicated "Inara API" board thread — not in the formal docs

Checked the actual long-running developer discussion thread (board 7049), not just the general bug-report board. Several concrete details Artie has stated there that the formal docs don't spell out:

- **Real hard rate limit: 2 requests/minute, maximum**, for apps that update user profiles — stricter than the docs' vague "be polite" language. Artie tightened this after discovering multiple simultaneous apps hammering the server with profile updates. Bots and lighter-weight apps get more headroom; anything needing more than 2/min should be discussed with him directly, not assumed.
- **Artie's own explicit guidance confirms our redirect**: for real-time market pricing, he tells developers to use **EDDN** (or static dumps), not the Inara API — privacy/scope-by-design, not an oversight. This matches what we'd already concluded independently, now confirmed from the source.
- **Whitelisting is fast and personal, not bureaucratic**: a short application (app name, purpose, data usage specifics, expected request frequency, a public description) got two different apps (a journal-reading copilot, and a materials-tracking companion — both close analogs to what we're planning) approved within 24 hours. Good sign for how this would likely go for us.
- **Journal loadout data gap, mechanism confirmed**: ship loadout only appears in the journal at session start or when swapping ships, not continuously — this is the same limitation Inara's own import FAQ mentioned, now with the actual cause. Relevant to `ship-build-advisor.md`'s "evaluate my existing build" feature.
- **New gap found, not previously flagged**: **pinned blueprints have no journal event at all** — they're invisible to any tool reading only the journal. If a future build-advisor feature wants to reference which blueprints a player has pinned (vs. just unlocked), there's currently no programmatic way to know that.

## Net effect on `ship-build-advisor.md`

- **Shopping-list feature (Feature C)**: Inara's API can't source this as originally assumed. Needs a different data path for "where to buy this module" — most likely EDDN's own outfitting/commodity schemas (which are read-access, no whitelisting conversation needed, and already covered in `tools-reference.md`) rather than Inara — and this is now Artie's own explicitly stated recommendation, not just our inference.
- **Permit readiness (Feature D)**: still blocked, and now confirmed Inara isn't the answer either — the earlier "check Inara's own permits page for how it sources this" open item is resolved as a dead end, not just unresearched.
- **New item for that doc**: pinned-blueprint tracking (if ever wanted) has no data source at all — journal-invisible, per the board thread above.
