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

    # Died's own shape decides opponent type (functional-requirements.md
    # 1.4/2.2): a Killers array with a "Cmdr <name>" entry -> Player; a
    # singular KillerName/KillerShip -> NPC; neither -> Self/Accident.
    deaths = query("""
        SELECT ship,
               CASE
                   WHEN EXISTS (
                       SELECT 1 FROM jsonb_array_elements(COALESCE(raw->'Killers', '[]'::jsonb)) k
                       WHERE (k->>'Name') LIKE 'Cmdr %%'
                   ) THEN 'Player'
                   WHEN raw ? 'KillerName' OR raw ? 'KillerShip' THEN 'NPC'
                   ELSE 'Self/Accident'
               END AS opponent_type,
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


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
