import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from psycopg2.pool import ThreadedConnectionPool

DATABASE_URL = os.environ["DATABASE_URL"]
pool: ThreadedConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
    yield
    pool.closeall()


app = FastAPI(lifespan=lifespan)


def query(sql: str, params=None) -> list[dict]:
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    finally:
        pool.putconn(conn)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/overview")
def overview():
    n_sessions = query("SELECT COUNT(*) AS n FROM sessions")[0]["n"]
    n_events = query("SELECT COUNT(*) AS n FROM events")[0]["n"]
    n_ships = query(
        "SELECT COUNT(DISTINCT ship) AS n FROM events "
        "WHERE ship != 'Unknown ship (before first Loadout)'"
    )[0]["n"]
    return {"sessions": n_sessions, "events": n_events, "ships": n_ships}


# Best-known community-sourced dates for major game updates (Frontier hasn't
# published a canonical list) -- used as reference lines on time-series
# charts. See functional-requirements.md 2.1.
GAME_UPDATES = [
    {"date": "2015-12-15", "label": "Horizons"},
    {"date": "2016-10-25", "label": "The Engineers"},
    {"date": "2018-02-27", "label": "Beyond Ch.1"},
    {"date": "2020-06-09", "label": "Fleet Carriers"},
    {"date": "2021-05-19", "label": "Odyssey"},
    {"date": "2025-03-27", "label": "Trailblazers/Colonisation"},
]


@app.get("/api/gameplay")
def gameplay():
    monthly = query("""
        SELECT to_char(date_trunc('month', session_start), 'YYYY-MM') AS month,
               COUNT(*) AS sessions,
               SUM(duration_hours) AS hours
        FROM sessions
        GROUP BY 1
        ORDER BY 1
    """)

    heatmap = query("""
        SELECT EXTRACT(DOW FROM session_start)::int AS dow,
               EXTRACT(HOUR FROM session_start)::int AS hour,
               COUNT(*) AS n
        FROM sessions
        GROUP BY 1, 2
    """)

    activity_mix = query("""
        SELECT to_char(date_trunc('month', "timestamp"), 'YYYY-MM') AS month,
               category,
               COUNT(*) AS n
        FROM events
        WHERE category IS NOT NULL AND category != 'Ambient'
        GROUP BY 1, 2
        ORDER BY 1
    """)

    # Valid-session window (0 < duration < 12h) per functional-requirements.md 1.1.
    histogram = query("""
        SELECT width_bucket(duration_hours, 0, 12, 12) AS bucket, COUNT(*) AS n
        FROM sessions
        WHERE duration_hours > 0 AND duration_hours < 12
        GROUP BY 1
        ORDER BY 1
    """)

    top_events = query("""
        SELECT event, COUNT(*) AS n
        FROM events
        GROUP BY event
        ORDER BY n DESC
        LIMIT 40
    """)

    return {
        "monthly": monthly,
        "heatmap": heatmap,
        "activity_mix": activity_mix,
        "histogram": histogram,
        "top_events": top_events,
        "game_updates": GAME_UPDATES,
    }


@app.get("/api/gameplay/event-trend")
def event_trend(event: str):
    monthly = query("""
        SELECT to_char(date_trunc('month', "timestamp"), 'YYYY-MM') AS month,
               COUNT(*) AS n
        FROM events
        WHERE event = %s
        GROUP BY 1
        ORDER BY 1
    """, (event,))
    return {"event": event, "monthly": monthly}


@app.get("/api/game-updates")
def game_updates():
    return GAME_UPDATES


# Excludes SRVs/suits (which also emit Loadout/LoadGame and get swept into
# ship attribution) and the pre-first-Loadout bucket from any "real ship"
# view. Applies only to the specific views functional-requirements.md 1.3
# names -- NOT a global filter. See module docstring above each query that
# uses it for which ones those are.
REAL_SHIP_FILTER = (
    "ship != 'Unknown ship (before first Loadout)' "
    "AND ship !~* 'testbuggy|utilitysuit|explorationsuit|tacticalsuit'"
)

# A Died event's own shape decides opponent type (functional-requirements.md
# 1.4/2.2/2.4): a Killers array with a "Cmdr <name>" entry -> Player; a
# singular KillerName/KillerShip -> NPC; neither -> Self/Accident. Shared
# between the Ships tab's deaths-by-ship split and Combat Analysis's
# ship-combat-death table so both stay byte-for-byte consistent.
#
# Known gap (see follow-up-todo.md, Combat section): a small number of Died
# events carry a *singular* KillerName that is itself "Cmdr <name>" (a
# player kill logged without a Killers array) -- this rule only checks the
# Killers-array shape, so those fall through to the NPC branch instead of
# Player. Confirmed in the live data (2 ship-state deaths, both to the same
# "Cmdr frank likes pie"); left as-is here to match the already-shipped
# Ships tab behavior rather than silently diverging between tabs.
DEATH_OPPONENT_TYPE_SQL = """CASE
                   WHEN EXISTS (
                       SELECT 1 FROM jsonb_array_elements(COALESCE(raw->'Killers', '[]'::jsonb)) k
                       WHERE (k->>'Name') LIKE 'Cmdr %%'
                   ) THEN 'Player'
                   WHEN raw ? 'KillerName' OR raw ? 'KillerShip' THEN 'NPC'
                   ELSE 'Self/Accident'
               END"""

# A ship's dominant activity category -- same "most events wins" rule as
# Play Patterns' per-session dominant category (SESSION_DOMINANT_CATEGORY_CTE
# above... well, below) and the frontend's dominantCategories() for the Ships
# tab, just computed in SQL here since Combat Analysis's death table needs it
# joined into a GROUP BY-free row set. Bare CTE-body fragment, same splicing
# convention as SESSION_NET_CREDITS_CTE.
SHIP_DOMINANT_CATEGORY_CTE = """
    ship_category_counts AS (
        SELECT ship, category, COUNT(*) AS n
        FROM events
        WHERE category IS NOT NULL AND category != 'Ambient' AND ship IS NOT NULL
        GROUP BY ship, category
    ),
    ship_dominant_category AS (
        SELECT DISTINCT ON (ship) ship, category AS dominant_category
        FROM ship_category_counts
        ORDER BY ship, n DESC, category ASC
    )
"""

# Module role recognition (functional-requirements.md 1.5): ordered
# substring match on the internal Elite `Item` name, first match wins.
# Order matters -- utility-mount items share the `hpt_` prefix with real
# weapons, so they must be listed before the generic `hpt_` fallback.
MODULE_ROLE_RULES = [
    ("int_shieldgenerator", "Shield Generator"),
    ("int_shieldcellbank", "Shield Cell Bank"),
    ("int_fuelscoop", "Fuel Scoop"),
    ("int_detailedsurfacescanner", "Detailed Surface Scanner"),
    ("int_dronecontrol_prospector", "Prospector Limpet Controller"),
    ("int_dronecontrol_collection", "Collector Limpet Controller"),
    ("int_dronecontrol_fueltransfer", "Fuel Transfer Limpet Controller"),
    ("int_dronecontrol_repair", "Repair Limpet Controller"),
    ("int_cargorack", "Cargo Rack"),
    ("int_passengercabin", "Passenger Cabin"),
    ("int_dockingcomputer", "Docking Computer"),
    ("hpt_heatsinklauncher", "Heat Sink Launcher"),
    ("hpt_shieldbooster", "Shield Booster"),
    ("hpt_chafflauncher", "Chaff Launcher"),
    ("hpt_electroniccountermeasure", "Electronic Countermeasure"),
    ("hpt_causticsinklauncher", "Caustic Sink Launcher"),
    ("hpt_plasmapointdefence", "Point Defence Turret"),
    ("hpt_crimescanner", "Kill Warrant Scanner"),
    ("hpt_cargoscanner", "Manifest Scanner"),
    ("hpt_", "Hardpoint-mounted module"),
]

# Fit-vs-usage flag rules (functional-requirements.md 2.2): module role ->
# (usage-evidence key, "rare" threshold as a fraction of that ship's total
# events). Zero evidence -> "Likely unnecessary"; below threshold -> "Worth
# reviewing"; at/above threshold -> no flag.
FIT_FLAG_RULES = {
    "Shield Generator": ("combat", 0.01),
    "Shield Cell Bank": ("combat", 0.01),
    "Fuel Scoop": ("fuelscoop", 0.005),
    "Detailed Surface Scanner": ("deep_explore", 0.01),
    "Hardpoint-mounted module": ("combat", 0.01),
}


def module_role(item: str) -> str | None:
    item_lower = item.lower()
    for substring, role in MODULE_ROLE_RULES:
        if substring in item_lower:
            return role
    return None


def evaluate_fit(loadouts: list[dict], evidence_by_ship: dict) -> tuple[list[dict], list[str]]:
    findings = []
    clean_ships = []
    for row in loadouts:
        ship = row["ship"]
        modules = (row["raw"] or {}).get("Modules") or []
        ev = evidence_by_ship.get(ship, {"combat": 0, "fuelscoop": 0, "deep_explore": 0, "total": 0})
        total = ev["total"] or 0
        ship_flags = []
        for m in modules:
            item = m.get("Item", "")
            role = module_role(item)
            if role not in FIT_FLAG_RULES:
                continue
            evidence_key, rare_threshold = FIT_FLAG_RULES[role]
            count = ev[evidence_key]
            pct = (count / total) if total else 0
            if count == 0:
                severity = "Likely unnecessary"
            elif pct < rare_threshold:
                severity = "Worth reviewing"
            else:
                continue
            if "Engineering" in m:
                severity += ", engineered"
            ship_flags.append({
                "ship": ship,
                "role": role,
                "slot": m.get("Slot", ""),
                "item": item,
                "severity": severity,
                "reason": f"{count} {evidence_key.replace('_', ' ')} event(s) out of "
                          f"{total} total logged for this ship ({pct:.2%})",
            })
        if ship_flags:
            findings.extend(ship_flags)
        else:
            clean_ships.append(ship)
    return findings, clean_ships


@app.get("/api/ships")
def ships():
    # Flight-hours: sum of contiguous same-ship spans (while actually
    # piloting it -- vehicle_state == SHIP, not off in an SRV or on foot)
    # within each session. LAG() flags where the ship changes; a running
    # SUM() of that flag turns "changed or not" into a span-group id, the
    # same trick functional-requirements.md 2.2 points at via the (broken)
    # "2.9" cross-reference -- see journal-visualization-tool.md's real
    # writeup of the original DuckDB version of this same idea.
    flight = query(f"""
        WITH ship_events AS (
            SELECT ship, source_file, "timestamp"
            FROM events
            WHERE vehicle_state = 'SHIP' AND ship IS NOT NULL
        ),
        tagged AS (
            SELECT *,
                   CASE WHEN LAG(ship) OVER w IS DISTINCT FROM ship THEN 1 ELSE 0 END AS new_span
            FROM ship_events
            WINDOW w AS (PARTITION BY source_file ORDER BY "timestamp")
        ),
        grouped AS (
            SELECT ship, source_file, "timestamp",
                   SUM(new_span) OVER (PARTITION BY source_file ORDER BY "timestamp"
                                        ROWS UNBOUNDED PRECEDING) AS grp
            FROM tagged
        ),
        spans AS (
            SELECT ship, source_file, grp,
                   MIN("timestamp") AS span_start, MAX("timestamp") AS span_end
            FROM grouped
            GROUP BY ship, source_file, grp
        )
        SELECT ship,
               SUM(EXTRACT(EPOCH FROM (span_end - span_start)) / 3600.0) AS flight_hours,
               COUNT(DISTINCT source_file) AS trips
        FROM spans
        WHERE {REAL_SHIP_FILTER}
        GROUP BY ship
    """)

    distance = query(f"""
        SELECT ship,
               SUM((raw->>'JumpDist')::double precision) AS light_years,
               COUNT(*) AS jumps
        FROM events
        WHERE event = 'FSDJump' AND ship IS NOT NULL AND {REAL_SHIP_FILTER}
        GROUP BY ship
    """)

    last_active = query(f"""
        SELECT ship, MAX("timestamp") AS last_active
        FROM events
        WHERE ship IS NOT NULL AND {REAL_SHIP_FILTER}
        GROUP BY ship
    """)
    # "Now" for idle-day calculations is the latest timestamp in the whole
    # dataset, not wall-clock today -- this DB is a manual, point-in-time
    # migration (see data-architecture.md), not a live feed. Using real
    # today would silently overstate every ship's idle time if the journal
    # hasn't been re-ingested recently.
    dataset_now = query('SELECT MAX("timestamp") AS now FROM events')[0]["now"]

    # Category x ship counts -- shared by three different features below
    # (dominant-category-per-ship, activity composition, coverage
    # concentration) rather than run three times. Not REAL_SHIP_FILTER'd:
    # functional-requirements.md 2.2 only scopes that exclusion to
    # fleet-overview/idle/coverage/flight-hours/distance, and composition
    # explicitly is not one of those -- coverage is, so that filtering
    # happens client-side, per-view, from this same shared result.
    category_by_ship = query("""
        SELECT ship, category, COUNT(*) AS n
        FROM events
        WHERE category IS NOT NULL AND category != 'Ambient' AND ship IS NOT NULL
        GROUP BY ship, category
    """)

    kills = query("""
        SELECT ship,
               COUNT(*) FILTER (WHERE event IN ('Bounty', 'FactionKillBond')) AS npc_kills,
               COUNT(*) FILTER (WHERE event = 'PVPKill') AS player_kills
        FROM events
        WHERE event IN ('Bounty', 'FactionKillBond', 'PVPKill') AND vehicle_state = 'SHIP'
        GROUP BY ship
    """)
    kills_excluded = query("""
        SELECT ship, COUNT(*) AS n
        FROM events
        WHERE event IN ('Bounty', 'FactionKillBond', 'PVPKill') AND vehicle_state != 'SHIP'
        GROUP BY ship
    """)

    # Died's own shape decides opponent type -- see DEATH_OPPONENT_TYPE_SQL
    # above (shared with Combat Analysis's death table).
    deaths = query(f"""
        SELECT ship,
               {DEATH_OPPONENT_TYPE_SQL} AS opponent_type,
               COUNT(*) AS n
        FROM events
        WHERE event = 'Died' AND vehicle_state = 'SHIP'
        GROUP BY ship, opponent_type
    """)
    deaths_excluded = query("""
        SELECT ship, COUNT(*) AS n
        FROM events
        WHERE event = 'Died' AND vehicle_state != 'SHIP'
        GROUP BY ship
    """)

    # Usage evidence for the fit-vs-usage table. Combat evidence is
    # vehicle_state-filtered (a shield generator only "counts" as used if
    # actual ship combat happened); fuel-scoop and deep-exploration evidence
    # are NOT -- ScanOrganic (deep exploration) fires on foot, so filtering
    # it to SHIP would falsely zero out every exobiology-active ship.
    evidence = query("""
        SELECT ship,
               COUNT(*) FILTER (WHERE category = 'Combat' AND vehicle_state = 'SHIP') AS combat,
               COUNT(*) FILTER (WHERE event = 'FuelScoop') AS fuelscoop,
               COUNT(*) FILTER (WHERE category = 'Exploration (deep)') AS deep_explore,
               COUNT(*) AS total
        FROM events
        WHERE ship IS NOT NULL
        GROUP BY ship
    """)

    loadouts = query(f"""
        SELECT DISTINCT ON (ship) ship, raw
        FROM events
        WHERE event = 'Loadout' AND ship IS NOT NULL AND {REAL_SHIP_FILTER}
        ORDER BY ship, "timestamp" DESC
    """)

    ship_list = query("""
        SELECT ship, COUNT(*) AS n
        FROM events
        WHERE ship IS NOT NULL AND category != 'Ambient'
        GROUP BY ship
        ORDER BY n DESC
    """)

    evidence_by_ship = {r["ship"]: r for r in evidence}
    fit_findings, fit_clean_ships = evaluate_fit(loadouts, evidence_by_ship)

    return {
        "flight": flight,
        "distance": distance,
        "last_active": last_active,
        "dataset_now": dataset_now,
        "category_by_ship": category_by_ship,
        "kills": kills,
        "kills_excluded": kills_excluded,
        "deaths": deaths,
        "deaths_excluded": deaths_excluded,
        "fit_findings": fit_findings,
        "fit_clean_ships": fit_clean_ships,
        "ship_list": ship_list,
    }


@app.get("/api/ships/mix")
def ship_mix(ship: str):
    monthly = query("""
        SELECT to_char(date_trunc('month', "timestamp"), 'YYYY-MM') AS month,
               category, COUNT(*) AS n
        FROM events
        WHERE ship = %s AND category IS NOT NULL AND category != 'Ambient'
        GROUP BY 1, 2
        ORDER BY 1
    """, (ship,))
    return {"ship": ship, "monthly": monthly}


# ---------------------------------------------------------------------------
# Net credits earned per session (functional-requirements.md 2.3). This is
# deliberately isolated as its own reusable CTE fragment -- 2.8's Session
# Spotlights tab (built later, by someone else) needs this exact per-session
# credit-delta logic and must NOT reimplement it.
#
# Sums a per-event-type credit_delta, grouped by session (source_file):
#   Bounty                   +TotalReward
#   FactionKillBond           +Reward
#   MissionCompleted          +Reward
#   MarketSell                +TotalSale
#   MarketBuy                 -TotalCost
#   SellExplorationData       +(BaseValue + Bonus)
#   MultiSellExplorationData  +TotalEarnings
#   RedeemVoucher              +Amount
#   SellOrganicData            +sum over BioData[] of (Value + Bonus)
# Every raw field is COALESCE'd to 0 -- a missing/null field (e.g. Bonus,
# which isn't always present) must not null out that event's contribution,
# which would otherwise poison the whole session's SUM() to NULL.
#
# This is a fragment of CTE bodies (no leading "WITH", no trailing comma) --
# splice it into a query's WITH clause, e.g.:
#   f"WITH {SESSION_NET_CREDITS_CTE} SELECT * FROM session_net_credits"
SESSION_NET_CREDITS_CTE = """
    session_credit_events AS (
        SELECT source_file,
               CASE event
                   WHEN 'Bounty' THEN
                       COALESCE((raw->>'TotalReward')::double precision, 0)
                   WHEN 'FactionKillBond' THEN
                       COALESCE((raw->>'Reward')::double precision, 0)
                   WHEN 'MissionCompleted' THEN
                       COALESCE((raw->>'Reward')::double precision, 0)
                   WHEN 'MarketSell' THEN
                       COALESCE((raw->>'TotalSale')::double precision, 0)
                   WHEN 'MarketBuy' THEN
                       -COALESCE((raw->>'TotalCost')::double precision, 0)
                   WHEN 'SellExplorationData' THEN
                       COALESCE((raw->>'BaseValue')::double precision, 0)
                       + COALESCE((raw->>'Bonus')::double precision, 0)
                   WHEN 'MultiSellExplorationData' THEN
                       COALESCE((raw->>'TotalEarnings')::double precision, 0)
                   WHEN 'RedeemVoucher' THEN
                       COALESCE((raw->>'Amount')::double precision, 0)
                   WHEN 'SellOrganicData' THEN (
                       SELECT COALESCE(SUM(
                           COALESCE((elem->>'Value')::double precision, 0)
                           + COALESCE((elem->>'Bonus')::double precision, 0)
                       ), 0)
                       FROM jsonb_array_elements(raw->'BioData') elem
                   )
                   ELSE 0
               END AS credit_delta
        FROM events
        WHERE event IN (
            'Bounty', 'FactionKillBond', 'MissionCompleted', 'MarketSell',
            'MarketBuy', 'SellExplorationData', 'MultiSellExplorationData',
            'RedeemVoucher', 'SellOrganicData'
        )
    ),
    session_net_credits AS (
        SELECT source_file, SUM(credit_delta) AS net_credits
        FROM session_credit_events
        GROUP BY source_file
    )
"""

# A session's dominant activity category (functional-requirements.md 2.3):
# the category with the most events in that session, excluding Ambient --
# the same "most events wins" rule as the Ships tab's per-ship dominant
# category (see frontend/app.js's dominantCategories()), just computed in
# SQL here since it feeds a GROUP BY / aggregate query rather than a chart
# color lookup. Also a bare CTE-body fragment, same splicing convention as
# SESSION_NET_CREDITS_CTE above.
SESSION_DOMINANT_CATEGORY_CTE = """
    session_category_counts AS (
        SELECT source_file, category, COUNT(*) AS n
        FROM events
        WHERE category IS NOT NULL AND category != 'Ambient'
        GROUP BY source_file, category
    ),
    session_dominant_category AS (
        SELECT DISTINCT ON (source_file) source_file, category AS dominant_category
        FROM session_category_counts
        ORDER BY source_file, n DESC, category ASC
    )
"""

# Valid sessions (0 < duration_hours < 12, functional-requirements.md 1.1)
# joined against net credits and dominant category -- the shared base for
# every Play Patterns feature below that needs per-session credit figures.
PLAY_PATTERNS_VALID_SESSIONS_CTE = f"""
    {SESSION_NET_CREDITS_CTE},
    {SESSION_DOMINANT_CATEGORY_CTE},
    valid_sessions AS (
        SELECT s.source_file,
               s.session_start,
               s.duration_hours,
               COALESCE(nc.net_credits, 0) AS net_credits,
               COALESCE(nc.net_credits, 0) / s.duration_hours AS credits_per_hour,
               COALESCE(dc.dominant_category, 'Other') AS dominant_category
        FROM sessions s
        LEFT JOIN session_net_credits nc ON nc.source_file = s.source_file
        LEFT JOIN session_dominant_category dc ON dc.source_file = s.source_file
        WHERE s.duration_hours > 0 AND s.duration_hours < 12
    )
"""


@app.get("/api/play-patterns")
def play_patterns():
    # Events-per-active-hour by category -- the direct evidence for why raw
    # event counts are a bad usage metric (functional-requirements.md 2.2/
    # 2.3): "active hour" = distinct hour-buckets containing >=1 event of
    # that category, so a category that fires many events per minute (e.g.
    # Combat) isn't just winning on density.
    tempo = query("""
        SELECT category,
               COUNT(*) AS events,
               COUNT(DISTINCT date_trunc('hour', "timestamp")) AS active_hours,
               COUNT(*)::double precision
                   / COUNT(DISTINCT date_trunc('hour', "timestamp")) AS events_per_active_hour
        FROM events
        WHERE category IS NOT NULL AND category != 'Ambient'
        GROUP BY category
        ORDER BY events_per_active_hour DESC
    """)

    scatter = query(f"""
        WITH {PLAY_PATTERNS_VALID_SESSIONS_CTE}
        SELECT duration_hours, net_credits, credits_per_hour, dominant_category
        FROM valid_sessions
    """)

    # Pearson correlation coefficients via Postgres's built-in corr(Y, X)
    # aggregate -- functional-requirements.md 2.3 explicitly wants these
    # computed server-side, not hand-rolled.
    correlations = query(f"""
        WITH {PLAY_PATTERNS_VALID_SESSIONS_CTE}
        SELECT corr(net_credits, duration_hours) AS duration_vs_total_credits,
               corr(credits_per_hour, duration_hours) AS duration_vs_credits_per_hour
        FROM valid_sessions
    """)[0]

    efficiency = query(f"""
        WITH {PLAY_PATTERNS_VALID_SESSIONS_CTE}
        SELECT dominant_category,
               COUNT(*) AS sessions,
               AVG(duration_hours) AS avg_duration_hours,
               AVG(net_credits) AS avg_net_credits,
               AVG(credits_per_hour) AS avg_credits_per_hour,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY credits_per_hour) AS median_credits_per_hour
        FROM valid_sessions
        GROUP BY dominant_category
        ORDER BY avg_credits_per_hour DESC
    """)

    top_lucrative = query(f"""
        WITH {PLAY_PATTERNS_VALID_SESSIONS_CTE}
        SELECT source_file, session_start, duration_hours, net_credits, dominant_category
        FROM valid_sessions
        ORDER BY net_credits DESC
        LIMIT 5
    """)

    top_longest = query(f"""
        WITH {PLAY_PATTERNS_VALID_SESSIONS_CTE}
        SELECT source_file, session_start, duration_hours, net_credits, dominant_category
        FROM valid_sessions
        ORDER BY duration_hours DESC
        LIMIT 5
    """)

    return {
        "tempo": tempo,
        "scatter": scatter,
        "correlations": correlations,
        "efficiency": efficiency,
        "top_lucrative": top_lucrative,
        "top_longest": top_longest,
    }


@app.get("/api/combat")
def combat():
    # 1. Most common bounty-kill opponents, fleet-wide (top 20). Bounty
    # vouchers are NPC-only (functional-requirements.md 2.2), vehicle_state
    # == SHIP only. `Target` is the internal Elite name (e.g. "cobramkiii")
    # and the stable grouping key -- present on every row. `Target_Localised`
    # (e.g. "Cobra Mk III") is missing on ~1/3 of rows and occasionally an
    # unresolved "$...;" localization token, so it's picked as a display-name
    # override only when present and not one of those tokens.
    bounty_opponents = query("""
        SELECT raw->>'Target' AS target,
               MAX(raw->>'Target_Localised') FILTER (
                   WHERE COALESCE(raw->>'Target_Localised', '') != ''
                     AND raw->>'Target_Localised' NOT LIKE '$%%'
               ) AS target_localised,
               COUNT(*) AS kills
        FROM events
        WHERE event = 'Bounty' AND vehicle_state = 'SHIP'
        GROUP BY 1
        ORDER BY kills DESC
        LIMIT 20
    """)

    # 2. Opponent mix per ship -- raw ship x opponent-target counts. The
    # top-8-ship x top-12-opponent-type cross-tab (functional-requirements.md
    # 2.4) is built client-side from this flat list, the same "flat rows in,
    # matrix in JS" pattern as the activity-mix charts elsewhere.
    opponent_by_ship = query("""
        SELECT ship, raw->>'Target' AS target, COUNT(*) AS n
        FROM events
        WHERE event = 'Bounty' AND vehicle_state = 'SHIP' AND ship IS NOT NULL
        GROUP BY ship, target
    """)

    # 3 & 6. Every recorded ship-combat death: vehicle_state == SHIP and
    # opponent_type is NPC or Player (excludes Self/Accident -- "ship
    # combat" specifically). Joined to each ship's own dominant activity
    # category for the overconfidence flag: a ship-combat death on a ship
    # whose dominant activity is NOT Combat. killer_ship/killer_rank fall
    # back from the singular KillerShip/KillerRank fields to the first
    # Killers[] array entry when only that shape is present.
    deaths = query(f"""
        WITH {SHIP_DOMINANT_CATEGORY_CTE},
        classified AS (
            SELECT ship, "timestamp",
                   COALESCE(NULLIF(raw->>'KillerShip', ''), raw->'Killers'->0->>'Ship') AS killer_ship,
                   COALESCE(NULLIF(raw->>'KillerRank', ''), raw->'Killers'->0->>'Rank') AS killer_rank,
                   {DEATH_OPPONENT_TYPE_SQL} AS opponent_type
            FROM events
            WHERE event = 'Died' AND vehicle_state = 'SHIP'
        )
        SELECT c.ship, c."timestamp", c.killer_ship, c.killer_rank, c.opponent_type,
               COALESCE(dc.dominant_category, 'Other') AS dominant_category,
               COALESCE(dc.dominant_category, 'Other') != 'Combat' AS overconfident
        FROM classified c
        LEFT JOIN ship_dominant_category dc ON dc.ship = c.ship
        WHERE c.opponent_type != 'Self/Accident'
        ORDER BY c."timestamp"
    """)

    # 4. Interdiction exposure by ship (top 15): the `Interdicted` event
    # fires when the player is the one interdicted (as opposed to the much
    # rarer `Interdiction` event, which is the player interdicting someone
    # else -- not "exposure" and not used here). Its own `Submitted` boolean
    # says whether the player submitted rather than fighting/escaping.
    interdiction_exposure = query("""
        SELECT ship,
               COUNT(*) AS times_interdicted,
               COUNT(*) FILTER (WHERE (raw->>'Submitted')::boolean) AS times_submitted
        FROM events
        WHERE event = 'Interdicted' AND vehicle_state = 'SHIP' AND ship IS NOT NULL
        GROUP BY ship
        ORDER BY times_interdicted DESC
        LIMIT 15
    """)

    # 5. Near-death events by ship (top 15): HullDamage with Health < 0.25,
    # vehicle_state == SHIP, and the event's own PlayerPilot == true (a
    # HullDamage event can fire for an NPC crew member or fighter pilot
    # instead of the commander -- PlayerPilot is false then).
    near_death = query("""
        SELECT ship, COUNT(*) AS near_deaths
        FROM events
        WHERE event = 'HullDamage'
          AND vehicle_state = 'SHIP'
          AND (raw->>'Health')::double precision < 0.25
          AND (raw->>'PlayerPilot')::boolean = true
          AND ship IS NOT NULL
        GROUP BY ship
        ORDER BY near_deaths DESC
        LIMIT 15
    """)

    return {
        "bounty_opponents": bounty_opponents,
        "opponent_by_ship": opponent_by_ship,
        "deaths": deaths,
        "interdiction_exposure": interdiction_exposure,
        "near_death": near_death,
    }


# ---------------------------------------------------------------------------
# Economy Analysis (functional-requirements.md 2.5). This is the whole point
# of the tab, so read this carefully before touching anything below:
#
# MarketSell does not record whether the sold cargo was bought (real trading)
# or mined (free). Confirmed by inspecting real rows in this DB: a commodity
# like painite has 1 MarketBuy event (10 units) ever, against 87 MarketSell
# events (16,321 units) -- so naively summing MarketSell - MarketBuy per
# commodity would count ~16,311 units of free mined cargo as "trading
# profit," a ~80x overstatement for painite alone (confirmed real bug in the
# original tool). So: any commodity this player has EVER mined at all (a
# MiningRefined event for it, anywhere in the whole history) is excluded from
# "pure trading" profit entirely. This deliberately UNDERSTATES trading
# profit for the handful of commodities that are legitimately both
# bought/sold and mined (gold, silver, palladium, platinum, tritium) -- the
# journal has no per-unit provenance to split "this unit was bought, that one
# was mined," so "count it all as mining" is the conservative, defensible
# choice, not a guess.
#
# A second, narrower exclusion applies identically everywhere below: a
# commodity with literally zero MarketBuy events anywhere in the dataset
# (e.g. mission-reward/salvage/colonization cargo picked up free and sold)
# is also excluded from "pure trade" -- otherwise it would show as pure
# profit with no corresponding fleet-wide cost, and the fleet-wide total
# would never reconcile against the sum of per-ship totals.
#
# Both exclusions are evaluated at the COMMODITY level, fleet-wide -- never
# per-ship. That's what makes the reconciliation hold: for every included
# commodity, fleet-wide profit is exactly the sum of that commodity's
# per-ship (sale - cost) splits by construction (summing the same numbers
# grouped a different way), so summing per-ship totals across every ship and
# every included commodity always equals the fleet-wide total. Verified live
# in economy() below (functional-requirements.md 5.5) -- this exact check
# caught a real bug in the original tool and must never regress.
#
# MiningRefined's own Type field is wrapped in Elite's internal localization
# token format (e.g. "$painite_name;"); MarketBuy/MarketSell's Type field is
# already a bare lowercase slug (e.g. "painite") -- confirmed by inspecting
# real rows, not assumed from memory. The join/exclusion normalizes
# MiningRefined's Type by stripping the "$" prefix and "_name;" suffix, then
# compares against MarketBuy/Sell's Type directly. Type_Localised is NOT used
# as a join key -- it's unreliable even within MiningRefined alone (e.g. the
# same Type shows up as both "Low Temp. Diamonds" and "Low Temperature
# Diamonds" on different rows) -- it's only used for a display label,
# picking one arbitrary-but-consistent non-empty value per commodity.
#
# Bare CTE-body fragment (no leading WITH, no trailing comma), same splicing
# convention as SESSION_NET_CREDITS_CTE above.
PURE_TRADE_CTE = """
    mined_commodities AS (
        SELECT DISTINCT regexp_replace(lower(raw->>'Type'), '^[$]|_name;$', '', 'g') AS commodity
        FROM events WHERE event = 'MiningRefined'
    ),
    market_sell AS (
        SELECT lower(raw->>'Type') AS commodity, ship,
               COALESCE((raw->>'TotalSale')::double precision, 0) AS total_sale,
               COALESCE((raw->>'Count')::double precision, 0) AS units
        FROM events WHERE event = 'MarketSell'
    ),
    market_buy AS (
        SELECT lower(raw->>'Type') AS commodity, ship,
               COALESCE((raw->>'TotalCost')::double precision, 0) AS total_cost,
               COALESCE((raw->>'Count')::double precision, 0) AS units
        FROM events WHERE event = 'MarketBuy'
    ),
    bought_commodities AS (
        SELECT DISTINCT commodity FROM market_buy
    ),
    pure_trade_commodities AS (
        SELECT commodity FROM bought_commodities
        WHERE commodity NOT IN (SELECT commodity FROM mined_commodities)
    ),
    commodity_names AS (
        SELECT lower(raw->>'Type') AS commodity, raw->>'Type_Localised' AS localised
        FROM events
        WHERE event IN ('MarketSell', 'MarketBuy')
          AND COALESCE(raw->>'Type_Localised', '') != ''
        UNION ALL
        SELECT regexp_replace(lower(raw->>'Type'), '^[$]|_name;$', '', 'g') AS commodity,
               raw->>'Type_Localised' AS localised
        FROM events
        WHERE event = 'MiningRefined' AND COALESCE(raw->>'Type_Localised', '') != ''
    ),
    commodity_display AS (
        SELECT commodity, MIN(localised) AS display
        FROM commodity_names
        GROUP BY commodity
    ),
    mining_sell_price AS (
        -- Player's own historical average sell price per unit, per
        -- commodity, from their actual MarketSell sales (functional-
        -- requirements.md 2.5: "that commodity's own historical average
        -- sell price," not a hardcoded game-wide price). Computed over ALL
        -- MarketSell rows for the commodity, not just pure-trade
        -- commodities -- a mined commodity like painite still needs its own
        -- real sell price to value the mined units.
        SELECT commodity, SUM(total_sale) / NULLIF(SUM(units), 0) AS avg_sell_price
        FROM market_sell
        GROUP BY commodity
    )
"""


@app.get("/api/economy")
def economy():
    # 1. Credits per active hour: trading vs mining. Same "active hour"
    # concept as Play Patterns' tempo chart (functional-requirements.md
    # 2.3/2.5): distinct hour-buckets containing >=1 event of that category.
    active_hours = query("""
        SELECT category, COUNT(DISTINCT date_trunc('hour', "timestamp")) AS active_hours
        FROM events
        WHERE category IN ('Trading', 'Mining')
        GROUP BY category
    """)

    # 2. Most profitable pure-trade commodities, top 15, plus the raw
    # sale/cost totals as evidence.
    trade_commodities = query(f"""
        WITH {PURE_TRADE_CTE},
        sale_by_commodity AS (
            SELECT commodity, SUM(total_sale) AS total_sale FROM market_sell GROUP BY commodity
        ),
        cost_by_commodity AS (
            SELECT commodity, SUM(total_cost) AS total_cost FROM market_buy GROUP BY commodity
        ),
        trade_commodity_profit AS (
            SELECT p.commodity,
                   COALESCE(sc.total_sale, 0) AS total_sale,
                   COALESCE(cc.total_cost, 0) AS total_cost,
                   COALESCE(sc.total_sale, 0) - COALESCE(cc.total_cost, 0) AS profit
            FROM pure_trade_commodities p
            LEFT JOIN sale_by_commodity sc ON sc.commodity = p.commodity
            LEFT JOIN cost_by_commodity cc ON cc.commodity = p.commodity
        )
        SELECT t.commodity, COALESCE(d.display, initcap(t.commodity)) AS display,
               t.total_sale, t.total_cost, t.profit
        FROM trade_commodity_profit t
        LEFT JOIN commodity_display d ON d.commodity = t.commodity
        ORDER BY t.profit DESC
        LIMIT 15
    """)

    # Fleet-wide pure-trade profit total across ALL included commodities
    # (not just the top 15) -- the number that must reconcile with the sum
    # of every ship's per-ship pure-trade profit below.
    fleet_trade_profit_total = query(f"""
        WITH {PURE_TRADE_CTE},
        sale_by_commodity AS (
            SELECT commodity, SUM(total_sale) AS total_sale FROM market_sell GROUP BY commodity
        ),
        cost_by_commodity AS (
            SELECT commodity, SUM(total_cost) AS total_cost FROM market_buy GROUP BY commodity
        )
        SELECT COALESCE(SUM(COALESCE(sc.total_sale, 0) - COALESCE(cc.total_cost, 0)), 0) AS total
        FROM pure_trade_commodities p
        LEFT JOIN sale_by_commodity sc ON sc.commodity = p.commodity
        LEFT JOIN cost_by_commodity cc ON cc.commodity = p.commodity
    """)[0]["total"]

    # 3. Most valuable mined commodities, top 15: units refined x the
    # commodity's own average sell price (see mining_sell_price above).
    mining_commodities = query(f"""
        WITH {PURE_TRADE_CTE},
        mined_commodity_totals AS (
            SELECT regexp_replace(lower(raw->>'Type'), '^[$]|_name;$', '', 'g') AS commodity,
                   COUNT(*) AS units_refined
            FROM events WHERE event = 'MiningRefined'
            GROUP BY commodity
        )
        SELECT m.commodity, COALESCE(d.display, initcap(m.commodity)) AS display,
               m.units_refined,
               COALESCE(p.avg_sell_price, 0) AS avg_sell_price,
               m.units_refined * COALESCE(p.avg_sell_price, 0) AS estimated_value
        FROM mined_commodity_totals m
        LEFT JOIN mining_sell_price p ON p.commodity = m.commodity
        LEFT JOIN commodity_display d ON d.commodity = m.commodity
        ORDER BY estimated_value DESC
        LIMIT 15
    """)

    fleet_mining_value_total = query(f"""
        WITH {PURE_TRADE_CTE},
        mined_commodity_totals AS (
            SELECT regexp_replace(lower(raw->>'Type'), '^[$]|_name;$', '', 'g') AS commodity,
                   COUNT(*) AS units_refined
            FROM events WHERE event = 'MiningRefined'
            GROUP BY commodity
        )
        SELECT COALESCE(SUM(m.units_refined * COALESCE(p.avg_sell_price, 0)), 0) AS total
        FROM mined_commodity_totals m
        LEFT JOIN mining_sell_price p ON p.commodity = m.commodity
    """)[0]["total"]

    # 4/6/7. Best-earning ship per activity. Trade profit is restricted to
    # the exact same pure-trade commodity set as the fleet-wide figure (see
    # PURE_TRADE_CTE) -- computed as sale-by-(ship,commodity) minus
    # cost-by-(ship,commodity), FULL OUTER JOINed so a ship that only sold
    # (or only bought) a commodity still gets a row. Cargo bought on one
    # ship and sold from another (a fleet-carrier transfer) legitimately
    # shows as a loss on the buyer and a gain on the seller -- this is a
    # correct description of which ship handled which side of the
    # transaction, not a bug (functional-requirements.md 2.5). Fetches ALL
    # ships (not just top 10) so the full sum can be reconciled against
    # fleet_trade_profit_total below.
    trade_by_ship_all = query(f"""
        WITH {PURE_TRADE_CTE},
        ship_sale AS (
            SELECT ship, commodity, SUM(total_sale) AS total_sale
            FROM market_sell
            WHERE ship IS NOT NULL AND commodity IN (SELECT commodity FROM pure_trade_commodities)
            GROUP BY ship, commodity
        ),
        ship_cost AS (
            SELECT ship, commodity, SUM(total_cost) AS total_cost
            FROM market_buy
            WHERE ship IS NOT NULL AND commodity IN (SELECT commodity FROM pure_trade_commodities)
            GROUP BY ship, commodity
        ),
        ship_commodity_profit AS (
            SELECT COALESCE(ss.ship, sc.ship) AS ship,
                   COALESCE(ss.total_sale, 0) - COALESCE(sc.total_cost, 0) AS profit
            FROM ship_sale ss
            FULL OUTER JOIN ship_cost sc ON sc.ship = ss.ship AND sc.commodity = ss.commodity
        )
        SELECT ship, SUM(profit) AS total_profit
        FROM ship_commodity_profit
        GROUP BY ship
        ORDER BY total_profit DESC
    """)

    mining_by_ship_all = query(f"""
        WITH {PURE_TRADE_CTE},
        mined_by_ship AS (
            SELECT ship, regexp_replace(lower(raw->>'Type'), '^[$]|_name;$', '', 'g') AS commodity,
                   COUNT(*) AS units_refined
            FROM events
            WHERE event = 'MiningRefined' AND ship IS NOT NULL
            GROUP BY ship, commodity
        )
        SELECT ship, SUM(units_refined * COALESCE(p.avg_sell_price, 0)) AS total_value
        FROM mined_by_ship mb
        LEFT JOIN mining_sell_price p ON p.commodity = mb.commodity
        GROUP BY ship
        ORDER BY total_value DESC
    """)

    # Reconciliation check (functional-requirements.md 2.5/5.5): the
    # fleet-wide pure-trade-profit total and the sum of every ship's
    # per-ship pure-trade profit must be the same number. Surfaced in the
    # response (not just asserted here) so the page can show this as the
    # raw evidence for its own correctness claim, per section 0's "every
    # heuristic must show its raw evidence."
    ship_sum_trade_profit = sum(r["total_profit"] or 0 for r in trade_by_ship_all)

    # 5. Raw evidence for the critical exclusion rule: commodities excluded
    # from "pure trade" because this player has also mined them at some
    # point, with how much MarketSell revenue that exclusion is keeping out
    # of the trading figures (painite chief among them -- see the module
    # docstring above).
    excluded_mined_but_sold = query(f"""
        WITH {PURE_TRADE_CTE},
        sale_by_commodity AS (
            SELECT commodity, SUM(total_sale) AS total_sale, SUM(units) AS units
            FROM market_sell GROUP BY commodity
        )
        SELECT s.commodity, COALESCE(d.display, initcap(s.commodity)) AS display,
               s.total_sale, s.units
        FROM sale_by_commodity s
        JOIN mined_commodities m ON m.commodity = s.commodity
        LEFT JOIN commodity_display d ON d.commodity = s.commodity
        ORDER BY s.total_sale DESC
    """)

    # Raw evidence for the second exclusion: commodities sold with zero
    # recorded MarketBuy events ever (mission-reward/salvage/colonization
    # cargo sold for a spurious "profit").
    excluded_zero_buy = query(f"""
        WITH {PURE_TRADE_CTE},
        sale_by_commodity AS (
            SELECT commodity, SUM(total_sale) AS total_sale, SUM(units) AS units
            FROM market_sell GROUP BY commodity
        )
        SELECT s.commodity, COALESCE(d.display, initcap(s.commodity)) AS display,
               s.total_sale, s.units
        FROM sale_by_commodity s
        LEFT JOIN commodity_display d ON d.commodity = s.commodity
        WHERE s.commodity NOT IN (SELECT commodity FROM mined_commodities)
          AND s.commodity NOT IN (SELECT commodity FROM bought_commodities)
        ORDER BY s.total_sale DESC
    """)

    active_hours_by_category = {r["category"]: r["active_hours"] for r in active_hours}

    return {
        "credits_per_active_hour": [
            {
                "category": "Trading",
                "credits": fleet_trade_profit_total,
                "active_hours": active_hours_by_category.get("Trading", 0),
            },
            {
                "category": "Mining",
                "credits": fleet_mining_value_total,
                "active_hours": active_hours_by_category.get("Mining", 0),
            },
        ],
        "trade_commodities": trade_commodities,
        "mining_commodities": mining_commodities,
        "trade_by_ship": trade_by_ship_all[:10],
        "mining_by_ship": mining_by_ship_all[:10],
        "excluded_mined_but_sold": excluded_mined_but_sold,
        "excluded_zero_buy": excluded_zero_buy,
        "reconciliation": {
            "fleet_total_pure_trade_profit": fleet_trade_profit_total,
            "ship_sum_pure_trade_profit": ship_sum_trade_profit,
        },
    }


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
