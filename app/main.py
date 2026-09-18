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


# ---------------------------------------------------------------------------
# Exploration Deep Dive (functional-requirements.md 2.6). The hard part of
# this tab: "primary (arrival) star type per system" and "which system was
# THIS event in" both require reconstructing system context from timestamps,
# not from the events table's own `star_system` column -- confirmed sparse in
# this dataset (populated on only ~7.4% of rows: 149,366 of 2,018,910) and,
# per the spec, unreliable across format eras even where it does exist (the
# precomputed lookup misses ~7-11% of pre-2018-format events).
#
# The reconstruction is a "gaps and islands" forward-fill, the same trick
# /api/ships already uses for ship flight-hours spans: COUNT(x) OVER (ORDER
# BY ...) only increments on non-null x, so it turns "has a marker appeared
# yet" into a stable running group id; MAX() over that group id then carries
# the marker's value forward to every row until the next one. The marker
# here is a StarSystem field on the nearest preceding FSDJump/Location/
# CarrierJump event *within the same session* (source_file) -- these three
# event types always carry StarSystem in this DB (confirmed: 100% coverage
# on all three, vs. 0% on ScanOrganic and ~91% on Scan).
#
# CRITICAL GOTCHA that cost real debugging time building this: computing the
# forward-filled MAX() OVER(...) and filtering WHERE id IS NOT NULL in the
# *same* SELECT is wrong -- a WHERE clause restricts which rows survive into
# the FROM that the window function's own PARTITION sees. Filter to "only
# the target rows" before MAX() OVER(PARTITION BY grp) runs, and each
# partition contains only other target rows (system_mark always NULL for
# those), so MAX() silently returns NULL for every single row -- a 100%
# failure with no error. Fixed by computing the forward-fill over the FULL
# combined (marker rows + target rows) set in one CTE, then filtering down
# to target rows in a separate, later CTE selecting FROM that result.
EXPLORATION_SYSTEM_MARKS_CTE = """
    exploration_system_marks AS (
        SELECT source_file, "timestamp", raw->>'StarSystem' AS system_mark
        FROM events
        WHERE event IN ('FSDJump', 'Location', 'CarrierJump') AND raw ? 'StarSystem'
    )
"""

# Primary (arrival) star per system, bucketed into the fixed <=8-column
# whitelist (functional-requirements.md 2.6/5.2 -- a 21-column one-per-star-
# type table was built and rejected twice before). "Primary star" = the Scan
# event with a StarType and DistanceFromArrivalLS ~ 0 (epsilon, not exact
# equality -- floats) in that system.
#
# Star-type-to-column mapping decision (the actual judgment call the spec
# asks to document): inspected every distinct raw StarType value in this DB
# (`SELECT DISTINCT raw->>'StarType' FROM events WHERE event='Scan'`) and
# found the 7 plain main-sequence letters (O, B, A, F, G, K, M) always occur
# as bare, unsuffixed codes, while every giant/supergiant/remnant/pre-main-
# sequence variant is a *different, longer* code that happens to start with
# one of those letters: K_OrangeGiant, M_RedGiant, M_RedSuperGiant,
# A_BlueWhiteSuperGiant, plus the white-dwarf family (DA/DC/DQ/DAZ), brown
# dwarfs (L/T/Y), T Tauri stars (TTS), carbon stars (C), S-type stars (S),
# neutron stars (N), and black holes (H). So the rule is an EXACT match
# against the 7 bare letters -- not a "starts with" / first-letter match,
# which would wrongly fold K_OrangeGiant into K's column and misrepresent a
# giant as an ordinary K dwarf. Everything else pools into "Other".
EXPLORATION_PRIMARY_STAR_CTE = f"""
    {EXPLORATION_SYSTEM_MARKS_CTE},
    primary_star_scans AS (
        SELECT id, source_file, "timestamp", raw->>'StarType' AS star_type
        FROM events
        WHERE event = 'Scan' AND COALESCE(raw->>'StarType', '') != ''
          AND (raw->>'DistanceFromArrivalLS')::double precision < 0.01
    ),
    primary_star_combined AS (
        SELECT source_file, "timestamp", system_mark, NULL::bigint AS id
        FROM exploration_system_marks
        UNION ALL
        SELECT source_file, "timestamp", NULL::text, id
        FROM primary_star_scans
    ),
    primary_star_tagged AS (
        SELECT *,
               COUNT(system_mark) OVER (
                   PARTITION BY source_file ORDER BY "timestamp", (system_mark IS NULL)
               ) AS grp
        FROM primary_star_combined
    ),
    primary_star_filled AS (
        SELECT id, MAX(system_mark) OVER (PARTITION BY source_file, grp) AS star_system
        FROM primary_star_tagged
    ),
    primary_star_resolved AS (
        SELECT f.id, f.star_system, s.star_type
        FROM primary_star_filled f
        JOIN primary_star_scans s ON s.id = f.id
        WHERE f.star_system IS NOT NULL
    ),
    system_primary_star AS (
        -- One row per system. A physical star's type doesn't change between
        -- visits, so any single deterministic reading is a reasonable,
        -- stable pick when a system was scanned on more than one visit.
        SELECT DISTINCT ON (star_system) star_system, star_type
        FROM primary_star_resolved
        ORDER BY star_system, star_type
    ),
    system_star_bucket AS (
        SELECT star_system, star_type,
               CASE WHEN star_type IN ('O', 'B', 'A', 'F', 'G', 'K', 'M') THEN star_type
                    ELSE 'Other' END AS bucket
        FROM system_primary_star
    )
"""

# High-value planet classes (functional-requirements.md 2.6): confirmed
# against real Scan rows' PlanetClass values, not assumed from memory.
HV_PLANET_CLASSES = (
    "Earthlike body", "Water world", "Ammonia world", "Water giant",
    "Gas giant with water based life", "Gas giant with ammonia based life",
)

# Fixed display order for the star-type hit-rate table's columns
# (functional-requirements.md 2.6/5.2: <=8 columns, never one per star type
# actually seen).
STAR_TYPE_BUCKET_ORDER = ["O", "B", "A", "F", "G", "K", "M", "Other"]

# Rare stellar phenomena worth calling out by name in the notable-finds
# narrative (functional-requirements.md 2.6) -- the spec names neutron
# star/black hole/carbon star/S-type/orange giant/red giant/"the two white-
# dwarf subtypes"; this DB's real StarType values (inspected directly) carry
# four distinct white-dwarf codes (DA/DC/DQ/DAZ) and two additional
# supergiant variants not explicitly named in the spec (red supergiant,
# blue-white supergiant) -- included anyway since they're real, rare finds
# in the data, not padding.
RARE_STAR_TYPES = {
    "N": "Neutron star",
    "H": "Black hole",
    "C": "Carbon star",
    "S": "S-type star",
    "K_OrangeGiant": "Orange giant",
    "M_RedGiant": "Red giant",
    "M_RedSuperGiant": "Red supergiant",
    "A_BlueWhiteSuperGiant": "Blue-white supergiant",
    "DA": "White dwarf (DA)",
    "DC": "White dwarf (DC)",
    "DQ": "White dwarf (DQ)",
    "DAZ": "White dwarf (DAZ)",
}


@app.get("/api/exploration")
def exploration():
    # 1. Discovery-type x primary-star-type hit-rate table -- the hard part
    # of this tab (functional-requirements.md 2.6). One combined pass:
    # primary-star resolution (for the column buckets) plus all 4 discovery
    # kinds, resolved to a system via the SAME timestamp-based mechanism in
    # a single window-function pass over their union, rather than four
    # separate (much more expensive) full CTE chains.
    #
    # "Pristine ring" = any Scan with ReserveLevel = PristineResources and a
    # non-empty Rings array (ReserveLevel is a body-level field, confirmed
    # against real rows -- not a per-ring field). "Pristine metallic ring" =
    # the same, further restricted to a ring entry with RingClass =
    # eRingClass_Metalic. "Biological find" = any CodexEntry with
    # SubCategory_Localised = 'Organic structures' (confirmed the real
    # subcategory label against the DB; a sibling 'Geology and anomalies'
    # subcategory under the same Category_Localised is NOT life and is
    # excluded).
    star_type_rows = query(f"""
        WITH {EXPLORATION_SYSTEM_MARKS_CTE},
        primary_star_scans AS (
            SELECT id, source_file, "timestamp", raw->>'StarType' AS star_type
            FROM events
            WHERE event = 'Scan' AND COALESCE(raw->>'StarType', '') != ''
              AND (raw->>'DistanceFromArrivalLS')::double precision < 0.01
        ),
        exploration_target_events AS (
            SELECT id, source_file, "timestamp", 'primary_star' AS kind FROM primary_star_scans
            UNION ALL
            SELECT id, source_file, "timestamp", 'hv_planet'
            FROM events
            WHERE event = 'Scan' AND raw->>'PlanetClass' IN %(hv_classes)s
            UNION ALL
            SELECT id, source_file, "timestamp", 'pristine_ring'
            FROM events
            WHERE event = 'Scan' AND raw->>'ReserveLevel' = 'PristineResources'
              AND jsonb_array_length(COALESCE(raw->'Rings', '[]'::jsonb)) > 0
            UNION ALL
            SELECT e.id, e.source_file, e."timestamp", 'pristine_metallic_ring'
            FROM events e
            WHERE e.event = 'Scan' AND e.raw->>'ReserveLevel' = 'PristineResources'
              AND EXISTS (
                  SELECT 1 FROM jsonb_array_elements(e.raw->'Rings') r
                  WHERE r->>'RingClass' = 'eRingClass_Metalic'
              )
            UNION ALL
            SELECT id, source_file, "timestamp", 'bio_find'
            FROM events
            WHERE event = 'CodexEntry' AND raw->>'SubCategory_Localised' = 'Organic structures'
        ),
        combined AS (
            SELECT source_file, "timestamp", system_mark, NULL::bigint AS id, NULL::text AS kind
            FROM exploration_system_marks
            UNION ALL
            SELECT source_file, "timestamp", NULL::text, id, kind
            FROM exploration_target_events
        ),
        tagged AS (
            SELECT *,
                   COUNT(system_mark) OVER (
                       PARTITION BY source_file ORDER BY "timestamp", (system_mark IS NULL)
                   ) AS grp
            FROM combined
        ),
        filled AS (
            SELECT id, kind, MAX(system_mark) OVER (PARTITION BY source_file, grp) AS star_system
            FROM tagged
        ),
        resolved AS (
            SELECT id, kind, star_system FROM filled WHERE id IS NOT NULL
        ),
        star_type_raw AS (
            SELECT r.id, r.star_system, e.raw->>'StarType' AS star_type
            FROM resolved r
            JOIN events e ON e.id = r.id
            WHERE r.kind = 'primary_star' AND r.star_system IS NOT NULL
        ),
        system_primary_star AS (
            SELECT DISTINCT ON (star_system) star_system, star_type
            FROM star_type_raw
            ORDER BY star_system, star_type
        ),
        bucketed AS (
            SELECT star_system,
                   CASE WHEN star_type IN ('O', 'B', 'A', 'F', 'G', 'K', 'M') THEN star_type
                        ELSE 'Other' END AS bucket
            FROM system_primary_star
        ),
        totals AS (
            SELECT bucket, COUNT(*) AS n_systems FROM bucketed GROUP BY bucket
        ),
        pivoted AS (
            SELECT b.bucket,
                COUNT(DISTINCT r.star_system) FILTER (WHERE r.kind = 'hv_planet') AS hv_planet_hits,
                COUNT(DISTINCT r.star_system) FILTER (WHERE r.kind = 'pristine_ring') AS pristine_ring_hits,
                COUNT(DISTINCT r.star_system)
                    FILTER (WHERE r.kind = 'pristine_metallic_ring') AS pristine_metallic_ring_hits,
                COUNT(DISTINCT r.star_system) FILTER (WHERE r.kind = 'bio_find') AS bio_find_hits
            FROM resolved r
            JOIN bucketed b ON b.star_system = r.star_system
            WHERE r.kind != 'primary_star' AND r.star_system IS NOT NULL
            GROUP BY b.bucket
        )
        SELECT t.bucket, t.n_systems,
               COALESCE(p.hv_planet_hits, 0) AS hv_planet_hits,
               COALESCE(p.pristine_ring_hits, 0) AS pristine_ring_hits,
               COALESCE(p.pristine_metallic_ring_hits, 0) AS pristine_metallic_ring_hits,
               COALESCE(p.bio_find_hits, 0) AS bio_find_hits
        FROM totals t
        LEFT JOIN pivoted p ON p.bucket = t.bucket
    """, {"hv_classes": HV_PLANET_CLASSES})
    star_type_by_bucket = {r["bucket"]: r for r in star_type_rows}
    star_type_table = [
        star_type_by_bucket.get(b, {
            "bucket": b, "n_systems": 0, "hv_planet_hits": 0, "pristine_ring_hits": 0,
            "pristine_metallic_ring_hits": 0, "bio_find_hits": 0,
        })
        for b in STAR_TYPE_BUCKET_ORDER
    ]

    # 2. Most profitable systems by exploration-data sale value (top 20).
    # SellExplorationData's Systems array and MultiSellExplorationData's
    # Discovered array each name several systems for one combined payout --
    # split evenly across every listed system, stated as an approximation
    # (functional-requirements.md 2.6: the journal doesn't itemize per-
    # system value within a bulk sale).
    #
    # Real data-quality quirk found while building this (also logged in
    # follow-up-todo.md): a small number of MultiSellExplorationData events
    # carry a blank "" SystemName on some (not all) of their Discovered
    # entries, alongside real names on the rest of the SAME event -- e.g.
    # event id 146063's Discovered array has 5 blank-named entries and one
    # named "Gliese 1081". The even-split-by-entry-count logic still applies
    # (matches what the game actually paid out per system), but a blank name
    # can't be attributed to any real system, so those entries are excluded
    # from the ranked list -- ~3.4% of total bulk exploration-data credits
    # end up unattributable this way, shown explicitly below rather than
    # silently folded into some placeholder row.
    system_sale_split = query(f"""
        WITH {EXPLORATION_PRIMARY_STAR_CTE},
        sale_split AS (
            SELECT sysname AS system,
                   (COALESCE((raw->>'BaseValue')::double precision, 0)
                    + COALESCE((raw->>'Bonus')::double precision, 0))
                   / NULLIF(jsonb_array_length(COALESCE(raw->'Systems', '[]'::jsonb)), 0) AS value
            FROM events, jsonb_array_elements_text(raw->'Systems') sysname
            WHERE event = 'SellExplorationData'
            UNION ALL
            SELECT elem->>'SystemName' AS system,
                   COALESCE((raw->>'TotalEarnings')::double precision, 0)
                   / NULLIF(jsonb_array_length(COALESCE(raw->'Discovered', '[]'::jsonb)), 0) AS value
            FROM events, jsonb_array_elements(raw->'Discovered') elem
            WHERE event = 'MultiSellExplorationData'
        ),
        system_totals AS (
            SELECT system, SUM(value) AS total_value
            FROM sale_split
            GROUP BY system
        )
        SELECT st.system, st.total_value, b.star_type, (b.bucket = 'Other') AS exotic,
               (st.system IS NULL OR st.system = '') AS unattributed
        FROM system_totals st
        LEFT JOIN system_star_bucket b ON b.star_system = st.system
        ORDER BY st.total_value DESC
    """)
    unattributed_value = sum(
        r["total_value"] or 0 for r in system_sale_split if r["unattributed"]
    )
    total_sale_value = sum(r["total_value"] or 0 for r in system_sale_split)
    profitable_systems = [r for r in system_sale_split if not r["unattributed"]][:20]

    # 3. Whether exotic-star-type systems earn a real exploration-credit
    # premium: mean credits for systems with vs. without an exotic primary
    # star, among the top 60 exploration-credit systems (functional-
    # requirements.md 2.6) -- reported as an observed comparison, not
    # asserted as fact either way. A meaningful chunk of even the top 60 have
    # no known primary star at all (never had an arrival-star Scan logged),
    # shown as its own "unknown" group rather than dropped silently.
    top60 = [r for r in system_sale_split if not r["unattributed"]][:60]
    exotic_group = [r["total_value"] for r in top60 if r["exotic"] is True]
    known_nonexotic_group = [r["total_value"] for r in top60 if r["exotic"] is False]
    unknown_group = [r["total_value"] for r in top60 if r["exotic"] is None]
    exotic_premium = {
        "exotic": {"n": len(exotic_group), "mean_credits": (sum(exotic_group) / len(exotic_group)) if exotic_group else None},
        "known_non_exotic": {
            "n": len(known_nonexotic_group),
            "mean_credits": (sum(known_nonexotic_group) / len(known_nonexotic_group)) if known_nonexotic_group else None,
        },
        "unknown_star": {
            "n": len(unknown_group),
            "mean_credits": (sum(unknown_group) / len(unknown_group)) if unknown_group else None,
        },
    }

    # 4. Most valuable systems for exobiology (top 20), from ScanOrganic
    # scans joined to the player's own historical average sale value per
    # species -- ScanOrganic and SellOrganicData are separate events with no
    # direct reference to each other, so this is an estimate (functional-
    # requirements.md 2.6), not an exact per-system sale figure. ScanOrganic
    # fires 3x per species (Log/Sample/Analyse); restricted to ScanType =
    # 'Log' (the first-logged record) so a species isn't triple-counted.
    # ScanOrganic carries no StarSystem field at all (confirmed: 0 of 6,526
    # rows) -- must use the same timestamp reconstruction as the hit-rate
    # table, not an optional nicety here.
    exobiology_systems = query(f"""
        WITH {EXPLORATION_SYSTEM_MARKS_CTE},
        scan_organic_log AS (
            SELECT id, source_file, "timestamp", raw->>'Species_Localised' AS species
            FROM events
            WHERE event = 'ScanOrganic' AND raw->>'ScanType' = 'Log'
        ),
        combined AS (
            SELECT source_file, "timestamp", system_mark, NULL::bigint AS id
            FROM exploration_system_marks
            UNION ALL
            SELECT source_file, "timestamp", NULL::text, id
            FROM scan_organic_log
        ),
        tagged AS (
            SELECT *,
                   COUNT(system_mark) OVER (
                       PARTITION BY source_file ORDER BY "timestamp", (system_mark IS NULL)
                   ) AS grp
            FROM combined
        ),
        filled AS (
            SELECT id, MAX(system_mark) OVER (PARTITION BY source_file, grp) AS star_system
            FROM tagged
        ),
        resolved AS (
            SELECT id, star_system FROM filled WHERE id IS NOT NULL
        ),
        species_value AS (
            SELECT elem->>'Species_Localised' AS species,
                   AVG(COALESCE((elem->>'Value')::double precision, 0)
                       + COALESCE((elem->>'Bonus')::double precision, 0)) AS avg_value,
                   COUNT(*) AS samples
            FROM events, jsonb_array_elements(raw->'BioData') elem
            WHERE event = 'SellOrganicData'
            GROUP BY 1
        )
        SELECT r.star_system, COUNT(*) AS species_logged,
               SUM(COALESCE(sv.avg_value, 0)) AS estimated_value
        FROM resolved r
        JOIN scan_organic_log s ON s.id = r.id
        LEFT JOIN species_value sv ON sv.species = s.species
        WHERE r.star_system IS NOT NULL AND r.star_system != ''
        GROUP BY r.star_system
        ORDER BY estimated_value DESC
        LIMIT 20
    """)

    # 5. Highest-value biological species analysed (top 15 by the player's
    # own average sale credits per sample) -- reuses the same species_value
    # logic as #4 above, standalone here since this view doesn't need any
    # system attribution at all.
    top_species = query("""
        SELECT elem->>'Species_Localised' AS species,
               AVG(COALESCE((elem->>'Value')::double precision, 0)
                   + COALESCE((elem->>'Bonus')::double precision, 0)) AS avg_value,
               COUNT(*) AS samples
        FROM events, jsonb_array_elements(raw->'BioData') elem
        WHERE event = 'SellOrganicData'
        GROUP BY 1
        ORDER BY avg_value DESC
        LIMIT 15
    """)

    # 6. First-time Codex discoveries by subcategory.
    codex_first_time = query("""
        SELECT raw->>'SubCategory_Localised' AS subcategory, COUNT(*) AS n
        FROM events
        WHERE event = 'CodexEntry' AND (raw->>'IsNewEntry')::boolean
        GROUP BY 1
        ORDER BY n DESC
    """)

    # 7. Notable/unusual finds narrative -- Thargoid Codex encounters,
    # chronological. CodexEntry rows carry System directly (confirmed: 1,816
    # of 1,816 CodexEntry rows have it) -- no reconstruction needed for this
    # one, unlike the hit-rate table above.
    thargoid_encounters = query("""
        SELECT "timestamp", raw->>'Name_Localised' AS name, raw->>'System' AS system
        FROM events
        WHERE event = 'CodexEntry' AND raw->>'SubCategory_Localised' = 'Thargoid objects'
        ORDER BY "timestamp"
    """)

    # 7b. Rare stellar phenomena visited: count + first-seen date (and
    # system, when the Scan event itself carries StarSystem -- true on ~91%
    # of Scan rows; not reconstructed for this narrative aside, unlike the
    # hit-rate table's primary-star column, since a missing system name here
    # is just a blank in a list, not a wrong denominator in a percentage).
    rare_star_rows = query("""
        SELECT raw->>'StarType' AS star_type, COUNT(*) AS n,
               MIN("timestamp") AS first_seen,
               (array_agg(raw->>'StarSystem' ORDER BY "timestamp"))[1] AS first_seen_system
        FROM events
        WHERE event = 'Scan' AND raw->>'StarType' = ANY(%s)
        GROUP BY 1
    """, (list(RARE_STAR_TYPES.keys()),))
    rare_star_by_type = {r["star_type"]: r for r in rare_star_rows}
    rare_stellar_phenomena = [
        {
            "star_type": st, "label": label,
            "n": rare_star_by_type[st]["n"] if st in rare_star_by_type else 0,
            "first_seen": rare_star_by_type[st]["first_seen"] if st in rare_star_by_type else None,
            "first_seen_system": rare_star_by_type[st]["first_seen_system"] if st in rare_star_by_type else None,
        }
        for st, label in RARE_STAR_TYPES.items()
    ]
    rare_stellar_phenomena = [r for r in rare_stellar_phenomena if r["n"] > 0]

    # 7c. Carryover callout: the single session with the highest combined
    # bulk exploration-data sale total, checked against how many of ITS OWN
    # named systems were actually visited (FSDJump/Location/CarrierJump)
    # within that same session -- the general mechanism functional-
    # requirements.md 2.7 calls the "carryover check" (Session Spotlights
    # isn't built yet in this app, so this is a narrow, one-session version
    # of the same idea, scoped to exploration data specifically).
    top_session = query("""
        SELECT source_file,
               SUM(CASE
                   WHEN event = 'SellExplorationData' THEN
                       COALESCE((raw->>'BaseValue')::double precision, 0)
                       + COALESCE((raw->>'Bonus')::double precision, 0)
                   WHEN event = 'MultiSellExplorationData' THEN
                       COALESCE((raw->>'TotalEarnings')::double precision, 0)
                   ELSE 0
               END) AS total_bulk_credits
        FROM events
        WHERE event IN ('SellExplorationData', 'MultiSellExplorationData')
        GROUP BY source_file
        ORDER BY total_bulk_credits DESC
        LIMIT 1
    """)
    carryover_outlier = None
    if top_session:
        source_file = top_session[0]["source_file"]
        session_meta = query(
            "SELECT session_start, duration_hours FROM sessions WHERE source_file = %s",
            (source_file,),
        )
        carryover_rows = query("""
            WITH named_systems AS (
                SELECT sysname AS system
                FROM events, jsonb_array_elements_text(raw->'Systems') sysname
                WHERE event = 'SellExplorationData' AND source_file = %(sf)s
                UNION ALL
                SELECT elem->>'SystemName' AS system
                FROM events, jsonb_array_elements(raw->'Discovered') elem
                WHERE event = 'MultiSellExplorationData' AND source_file = %(sf)s
            ),
            visited AS (
                SELECT DISTINCT raw->>'StarSystem' AS system
                FROM events
                WHERE event IN ('FSDJump', 'Location', 'CarrierJump')
                  AND source_file = %(sf)s AND raw ? 'StarSystem'
            )
            SELECT n.system, (n.system IN (SELECT system FROM visited)) AS visited_this_session
            FROM named_systems n
            WHERE n.system IS NOT NULL AND n.system != ''
        """, {"sf": source_file})
        named = [r["system"] for r in carryover_rows]
        not_visited = [r["system"] for r in carryover_rows if not r["visited_this_session"]]
        carryover_outlier = {
            "source_file": source_file,
            "session_start": session_meta[0]["session_start"] if session_meta else None,
            "total_bulk_credits": top_session[0]["total_bulk_credits"],
            "named_systems_count": len(named),
            "not_visited_count": len(not_visited),
            "pct_carried_over": (len(not_visited) / len(named) * 100) if named else 0,
            "examples": sorted(not_visited)[:8],
        }

    return {
        "star_type_table": star_type_table,
        "profitable_systems": profitable_systems,
        "unattributed_sale_value": unattributed_value,
        "total_sale_value": total_sale_value,
        "exotic_premium": exotic_premium,
        "exobiology_systems": exobiology_systems,
        "top_species": top_species,
        "codex_first_time": codex_first_time,
        "thargoid_encounters": thargoid_encounters,
        "rare_stellar_phenomena": rare_stellar_phenomena,
        "carryover_outlier": carryover_outlier,
    }


# ---------------------------------------------------------------------------
# Surface Activity (functional-requirements.md 2.7). Vehicle-state span
# computation is the shared foundation for every feature on this tab: the
# events table's own vehicle_state column (populated at migration time by
# the 1.4 state machine over LaunchSRV/DockSRV/SRVDestroyed/Disembark/Embark)
# is grouped into contiguous same-state runs per session via the exact
# LAG()-plus-running-SUM() trick /api/ships uses for ship flight-hours (see
# the comment on that query) -- tracking vehicle_state transitions instead of
# ship-identity transitions. The one deliberate difference: a span's END here
# is the START of the very next contiguous run (or session end for the last
# run), not that run's own last event's timestamp. On-foot events are
# comparatively sparse, so ending a span at its own last event would badly
# undercount short excursions (functional-requirements.md 2.7 says this
# explicitly) -- ending at the next boundary event's timestamp instead
# captures the whole excursion, interior event density or not.
#
# Known gap (see follow-up-todo.md's open "vehicle-state default-to-SHIP"
# item, confirmed to also reach this tab while building it): a session that
# opens (LoadGame) mid-SRV/on-foot excursion, before any correcting boundary
# event fires within that same session, has its opening stretch of events
# wrongly tagged vehicle_state=SHIP -- so any real excursion time before the
# first boundary event in such a session is invisible to this tab's SRV/FOOT
# spans entirely (it falls into an excluded SHIP-state group instead).
# Confirmed non-zero here: 121 BackpackChange + 1 CollectItems event
# (on-foot-only actions -- they cannot fire from inside a ship) carry
# vehicle_state=SHIP; see default_to_ship_gap_evidence below and the
# follow-up-todo.md addendum.
VEHICLE_SPANS_CTE = """
    vehicle_events AS (
        SELECT id, source_file, "timestamp", vehicle_state, event, category
        FROM events
        WHERE vehicle_state IS NOT NULL
    ),
    vehicle_tagged AS (
        SELECT *,
               CASE WHEN LAG(vehicle_state) OVER w IS DISTINCT FROM vehicle_state THEN 1 ELSE 0 END AS new_span
        FROM vehicle_events
        WINDOW w AS (PARTITION BY source_file ORDER BY "timestamp")
    ),
    vehicle_grouped AS (
        SELECT *,
               SUM(new_span) OVER (PARTITION BY source_file ORDER BY "timestamp"
                                    ROWS UNBOUNDED PRECEDING) AS grp
        FROM vehicle_tagged
    ),
    vehicle_span_bounds AS (
        SELECT source_file, grp, vehicle_state, MIN("timestamp") AS span_start
        FROM vehicle_grouped
        GROUP BY source_file, grp, vehicle_state
    ),
    vehicle_span_next AS (
        SELECT *,
               LEAD(span_start) OVER (PARTITION BY source_file ORDER BY span_start) AS next_start
        FROM vehicle_span_bounds
    ),
    vehicle_spans AS (
        -- Zero-duration spans (two boundary events logged in the same
        -- second) are dropped here, not left to distort per-span averages.
        SELECT vsn.source_file, vsn.grp, vsn.vehicle_state, vsn.span_start,
               COALESCE(vsn.next_start, sess.session_end) AS span_end
        FROM vehicle_span_next vsn
        JOIN sessions sess ON sess.source_file = vsn.source_file
        WHERE vsn.vehicle_state IN ('SRV', 'FOOT')
          AND COALESCE(vsn.next_start, sess.session_end) > vsn.span_start
    )
"""

# Mission windows (functional-requirements.md 1.6): MissionAccepted to the
# first of MissionCompleted/MissionFailed/MissionAbandoned, or that mission's
# own Expiry when never resolved (~1% of missions -- confirmed live: 4,943
# accepted vs. 4,937 resolved, 0.12%, and only 5 missions lack both a
# resolution AND an Expiry, falling back to a zero-width window at their own
# accepted_at -- a safe, conservative default). MissionAccepted's own Name
# field (confirmed against real rows) is the raw mission-type token, e.g.
# "Mission_Courier_Elections" / "MISSION_Salvage_Illegal" -- confirmed it
# never carries the "_name" suffix itself (only MissionCompleted/Failed/
# Abandoned's own Name field does, e.g. "Mission_Courier_Elections_name");
# both the prefix and suffix are stripped here anyway, per spec, for
# robustness against any format this hasn't been checked against.
MISSION_WINDOWS_CTE = """
    mission_accepted AS (
        SELECT (raw->>'MissionID')::bigint AS mission_id,
               "timestamp" AS accepted_at,
               raw->>'Name' AS mission_name,
               (raw->>'Expiry')::timestamp AS expiry
        FROM events
        WHERE event = 'MissionAccepted' AND raw ? 'MissionID'
    ),
    mission_resolved AS (
        SELECT (raw->>'MissionID')::bigint AS mission_id, MIN("timestamp") AS resolved_at
        FROM events
        WHERE event IN ('MissionCompleted', 'MissionFailed', 'MissionAbandoned')
          AND raw ? 'MissionID'
        GROUP BY 1
    ),
    mission_windows AS (
        SELECT ma.mission_id, ma.accepted_at, ma.mission_name,
               COALESCE(mr.resolved_at, ma.expiry, ma.accepted_at) AS window_end
        FROM mission_accepted ma
        LEFT JOIN mission_resolved mr ON mr.mission_id = ma.mission_id
    )
"""

# Excursion-to-mission overlap rule (functional-requirements.md 1.6/2.7): a
# span counts as "under a mission" if it overlaps ANY active mission window
# at all -- co-occurrence, not proof of causation, a real limitation stated
# explicitly on the page rather than hidden. Bare CTE-body fragment chaining
# both fragments above, same splicing convention as SESSION_NET_CREDITS_CTE.
SURFACE_SPAN_MISSION_CTE = f"""
    {VEHICLE_SPANS_CTE},
    {MISSION_WINDOWS_CTE},
    span_mission_overlap AS (
        SELECT vs.source_file, vs.grp, vs.vehicle_state, vs.span_start, vs.span_end,
               EXISTS (
                   SELECT 1 FROM mission_windows mw
                   WHERE mw.accepted_at < vs.span_end AND mw.window_end > vs.span_start
               ) AS under_mission
        FROM vehicle_spans vs
    )
"""

# On-foot/SRV-specific category overrides (functional-requirements.md 2.7) --
# scoped to THIS tab only, not the shared events.category map used
# everywhere else. Checked first; any event not in this list falls back to
# its already-computed category column.
SURFACE_CATEGORY_CASE = """CASE
                       WHEN vg.event = 'CommitCrime' THEN 'Combat'
                       WHEN vg.event IN ('BackpackChange', 'CollectItems', 'DropItems',
                                         'CollectCargo', 'ShipLocker', 'Backpack')
                           THEN 'Looting/Inventory'
                       WHEN vg.event = 'SuitLoadout' THEN 'Ship management'
                       WHEN vg.event = 'DatalinkScan' THEN 'Exploration (deep)'
                       WHEN vg.event IN ('LaunchSRV', 'DockSRV', 'Disembark', 'Embark',
                                         'Touchdown', 'Liftoff')
                           THEN 'Travel'
                       ELSE COALESCE(vg.category, 'Other')
                   END"""


@app.get("/api/surface")
def surface():
    # All three metrics below (hours, category composition, mission-type
    # overlap) share the same expensive foundation -- the vehicle_grouped
    # window-function pass over ~2M events, plus the mission_windows/
    # span_mission_overlap CTEs. Run as three separate queries this cost
    # gets paid three times over (confirmed while building this: ~14-22s
    # each). Combined into ONE query via UNION ALL instead: every shared CTE
    # is referenced more than once, so Postgres auto-materializes each one
    # rather than inlining/recomputing it per reference -- the whole
    # endpoint costs about the same as one pass (~20s, in line with
    # /api/ships' comparable flight-hours window-function query, already
    # shipped at a similar cost). Rows are tagged by a `metric` discriminator
    # column and split apart in Python below.
    rows = query(f"""
        WITH {SURFACE_SPAN_MISSION_CTE},
        hours_metric AS (
            SELECT 'hours' AS metric, vehicle_state, under_mission,
                   NULL::text AS category, NULL::text AS mission_type,
                   COUNT(*) AS n,
                   SUM(EXTRACT(EPOCH FROM (span_end - span_start)) / 3600.0) AS hours
            FROM span_mission_overlap
            GROUP BY vehicle_state, under_mission
        ),
        -- Activity-category composition, faceted by (state x mission-status).
        -- Ambient is excluded post-override, matching this report's usual
        -- activity-mix default (functional-requirements.md 1.2) -- the
        -- override list above already pulls the real on-foot/SRV activity
        -- (looting, travel, combat, etc.) out of what would otherwise land
        -- in Ambient; what's left tagged Ambient here is mostly Music-event
        -- noise (about 7 percent of all on-foot/SRV events fleet-wide), not
        -- a real activity.
        composition_events AS (
            SELECT smo.vehicle_state, smo.under_mission,
                   {SURFACE_CATEGORY_CASE} AS category
            FROM vehicle_grouped vg
            JOIN span_mission_overlap smo ON smo.source_file = vg.source_file AND smo.grp = vg.grp
        ),
        composition_metric AS (
            SELECT 'composition' AS metric, vehicle_state, under_mission, category,
                   NULL::text AS mission_type, COUNT(*) AS n, NULL::double precision AS hours
            FROM composition_events
            WHERE category != 'Ambient'
            GROUP BY 2, 3, 4
        ),
        -- Most common mission types overlapping an excursion, on-foot and
        -- SRV side by side (top 10 each, picked in Python below) --
        -- DISTINCT on (span, mission) first so a mission active across a
        -- long excursion isn't multi-counted for that one excursion; a
        -- mission overlapping several different excursions legitimately
        -- counts once per excursion.
        excursion_missions AS (
            SELECT DISTINCT smo.source_file, smo.grp, smo.vehicle_state, mw.mission_id, mw.mission_name
            FROM span_mission_overlap smo
            JOIN mission_windows mw
              ON mw.accepted_at < smo.span_end AND mw.window_end > smo.span_start
            WHERE smo.under_mission
        ),
        mission_type_metric AS (
            SELECT 'mission_type' AS metric, vehicle_state, NULL::boolean AS under_mission,
                   NULL::text AS category,
                   replace(regexp_replace(regexp_replace(mission_name, '^(Mission_|MISSION_|Chain_)', '', 'i'),
                                          '_name$', '', 'i'), '_', ' ') AS mission_type,
                   COUNT(*) AS n, NULL::double precision AS hours
            FROM excursion_missions
            GROUP BY 2, 5
        )
        SELECT * FROM hours_metric
        UNION ALL SELECT * FROM composition_metric
        UNION ALL SELECT * FROM mission_type_metric
    """)
    hours_rows = [r for r in rows if r["metric"] == "hours"]
    composition_rows = [r for r in rows if r["metric"] == "composition"]
    mission_type_rows = sorted(
        (r for r in rows if r["metric"] == "mission_type"), key=lambda r: -r["n"]
    )

    # Raw evidence for the known vehicle-state default-to-SHIP gap (see the
    # module comment above VEHICLE_SPANS_CTE) -- events that can only fire
    # on foot but are tagged vehicle_state=SHIP, meaning some real on-foot
    # time at the very start of a session is invisible to this tab's span
    # computation entirely. Shown on the page rather than swept under the
    # rug (functional-requirements.md 0: every heuristic shows its evidence).
    default_gap_evidence = query("""
        SELECT event, COUNT(*) AS n
        FROM events
        WHERE event IN ('BackpackChange', 'CollectItems', 'DropItems') AND vehicle_state = 'SHIP'
        GROUP BY 1
        ORDER BY 2 DESC
    """)

    hours_by_facet = {(r["vehicle_state"], r["under_mission"]): r for r in hours_rows}

    def facet_hours(state, mission):
        r = hours_by_facet.get((state, mission))
        return {"hours": (r["hours"] or 0) if r else 0, "spans": r["n"] if r else 0}

    foot_mission = facet_hours("FOOT", True)
    foot_free = facet_hours("FOOT", False)
    srv_mission = facet_hours("SRV", True)
    srv_free = facet_hours("SRV", False)
    foot_total = foot_mission["hours"] + foot_free["hours"]
    srv_total = srv_mission["hours"] + srv_free["hours"]

    # Top category per facet -- recomputed live from composition_rows above
    # (functional-requirements.md 2.7: the narrative summary must be
    # recomputed from live data, not hardcoded), used for "what that time is
    # actually spent on" in the narrative.
    def top_category(state, mission):
        rows = [r for r in composition_rows if r["vehicle_state"] == state and r["under_mission"] == mission]
        if not rows:
            return None
        return max(rows, key=lambda r: r["n"])["category"]

    return {
        "hours_summary": {
            "on_foot": {
                "mission_hours": foot_mission["hours"],
                "free_hours": foot_free["hours"],
                "total_hours": foot_total,
                "mission_spans": foot_mission["spans"],
                "free_spans": foot_free["spans"],
                "pct_under_mission": (foot_mission["hours"] / foot_total * 100) if foot_total else 0,
            },
            "srv": {
                "mission_hours": srv_mission["hours"],
                "free_hours": srv_free["hours"],
                "total_hours": srv_total,
                "mission_spans": srv_mission["spans"],
                "free_spans": srv_free["spans"],
                "pct_under_mission": (srv_mission["hours"] / srv_total * 100) if srv_total else 0,
            },
        },
        "composition": composition_rows,
        "mission_types_on_foot": [r for r in mission_type_rows if r["vehicle_state"] == "FOOT"][:10],
        "mission_types_srv": [r for r in mission_type_rows if r["vehicle_state"] == "SRV"][:10],
        "narrative": {
            "on_foot_mission_top_category": top_category("FOOT", True),
            "on_foot_free_top_category": top_category("FOOT", False),
            "srv_mission_top_category": top_category("SRV", True),
            "srv_free_top_category": top_category("SRV", False),
        },
        "default_to_ship_gap_evidence": default_gap_evidence,
    }


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
