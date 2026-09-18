#!/usr/bin/env python3
"""
One-time migration: journal.duckdb -> Postgres (EDna's `events`/`sessions`
tables).

Why this still uses DuckDB, even though the app itself won't: DuckDB's ASOF
JOIN is exactly the right tool for "attribute this event to whichever ship's
Loadout was most recently seen at or before it" (see
functional-requirements.md 1.3/1.4) -- Postgres has no equivalent join type.
Rather than reimplement that logic by hand in Postgres SQL (slow, easy to
get subtly wrong), this script reuses DuckDB's ASOF join ONE TIME, against
the existing journal.duckdb file, to precompute category/ship/vehicle_state
for every event -- then bulk-loads the *result* into Postgres. The live app
never touches DuckDB; this script is the only place it's used.

Usage:
    python migrate.py <path-to-journal.duckdb> <postgres-dsn>

Example (from WSL2, journal.duckdb on the Windows D: drive):
    python migrate.py /mnt/d/Elite/journal.duckdb \
        "postgresql://edna_app:PASSWORD@localhost:5432/edna"

Note: use `localhost` here (not `lab-postgres`) -- this script runs directly
on your host/WSL2, not inside a container on the `web` Docker network.
"""

import io
import json
import sys

import duckdb
import pandas as pd
import psycopg2

# ---------------------------------------------------------------------------
# Ported from journal_common.py -- must stay in sync with
# functional-requirements.md section 1.2 if either ever changes.
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    "UnderAttack": "Combat", "Died": "Combat", "Interdicted": "Combat",
    "Interdiction": "Combat", "PVPKill": "Combat", "Bounty": "Combat",
    "FactionKillBond": "Combat", "ShipTargeted": "Combat", "HullDamage": "Combat",
    "ShieldState": "Combat", "EscapeInterdiction": "Combat",
    "FSSSignalDiscovered": "Exploration (transit)",
    "FSSDiscoveryScan": "Exploration (transit)", "FSSAllBodiesFound": "Exploration (transit)",
    "NavBeaconScan": "Exploration (transit)",
    "SAAScanComplete": "Exploration (deep)", "SAASignalsFound": "Exploration (deep)",
    "DiscoveryScan": "Exploration (deep)", "MultiSellExplorationData": "Exploration (deep)",
    "SellExplorationData": "Exploration (deep)", "CodexEntry": "Exploration (deep)",
    "ScanOrganic": "Exploration (deep)", "SellOrganicData": "Exploration (deep)",
    "MarketBuy": "Trading", "MarketSell": "Trading", "Market": "Trading",
    "Trade": "Trading", "BuyTradeData": "Trading",
    "MiningRefined": "Mining", "ProspectedAsteroid": "Mining",
    "AsteroidCracked": "Mining", "LaunchDrone": "Mining",
    "Friends": "Social", "ReceiveText": "Social", "SendText": "Social",
    "CrewAssign": "Social", "CrewLaunchFighter": "Social", "CrewMemberJoins": "Social",
    "CrewMemberQuits": "Social", "JoinACrew": "Social", "QuitACrew": "Social",
    "WingAdd": "Social", "WingJoin": "Social", "WingLeave": "Social",
    "SquadronStartup": "Social",
    "Missions": "Passengers/Missions", "MissionAccepted": "Passengers/Missions",
    "MissionCompleted": "Passengers/Missions", "MissionFailed": "Passengers/Missions",
    "MissionAbandoned": "Passengers/Missions", "MissionRedirected": "Passengers/Missions",
    "EngineerCraft": "Engineering", "EngineerProgress": "Engineering",
    "EngineerContribution": "Engineering", "MaterialCollected": "Engineering",
    "MaterialDiscarded": "Engineering", "Synthesis": "Engineering",
    "MaterialTrade": "Engineering",
    "ColonisationConstructionDepot": "Colonisation",
    "ColonisationContribution": "Colonisation", "ColonisationSystemClaim": "Colonisation",
    "ColonisationBeaconDeployed": "Colonisation",
    "Docked": "Travel", "Undocked": "Travel", "DockingRequested": "Travel",
    "DockingGranted": "Travel", "DockingDenied": "Travel", "StartJump": "Travel",
    "FSDJump": "Travel", "SupercruiseEntry": "Travel", "SupercruiseExit": "Travel",
    "Location": "Travel", "Touchdown": "Travel", "Liftoff": "Travel",
    "ApproachBody": "Travel", "LeaveBody": "Travel", "ApproachSettlement": "Travel",
    "NavRoute": "Travel", "NavRouteClear": "Travel", "SupercruiseDestinationDrop": "Travel",
    "CarrierJump": "Travel", "CarrierLocation": "Travel",
    "FuelScoop": "Travel", "ReservoirReplenished": "Travel",
    "Loadout": "Ship management", "ShipyardBuy": "Ship management",
    "ShipyardSell": "Ship management", "ShipyardSwap": "Ship management",
    "ShipyardTransfer": "Ship management", "ModuleBuy": "Ship management",
    "ModuleSell": "Ship management", "ModuleRetrieve": "Ship management",
    "ModuleStore": "Ship management", "StoredShips": "Ship management",
    "StoredModules": "Ship management", "Repair": "Ship management",
    "RefuelAll": "Ship management", "BuyAmmo": "Ship management",
    "Cargo": "Ship management", "ShipLocker": "Ship management",
    "Materials": "Ship management",
    "Music": "Ambient", "Progress": "Ambient", "Rank": "Ambient",
    "Statistics": "Ambient", "Fileheader": "Ambient", "Commander": "Ambient",
}

NON_SHIP_DISPLAY_SUBSTRINGS = (
    "testbuggy", "utilitysuit", "explorationsuit", "tacticalsuit",
    "unknown ship (before first loadout)",
)


def categorize(event: str, scan_type: str = None) -> str:
    if event.startswith("Powerplay"):
        return "Powerplay"
    if event == "Scan":
        return "Exploration (transit)" if scan_type == "AutoScan" else "Exploration (deep)"
    return CATEGORY_MAP.get(event, "Other")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    duckdb_path, pg_dsn = sys.argv[1], sys.argv[2]

    print(f"Connecting to {duckdb_path} (read-only) ...")
    con = duckdb.connect(duckdb_path, read_only=True)

    print("Building ship attribution views (mirrors journal_common.py) ...")
    con.execute("""
        CREATE OR REPLACE TEMP VIEW ship_changes AS
        SELECT timestamp,
               json_extract_string(raw, '$.ShipID') AS ship_id,
               json_extract_string(raw, '$.Ship') AS ship_type,
               NULLIF(TRIM(json_extract_string(raw, '$.ShipName')), '') AS ship_name,
               NULLIF(json_extract_string(raw, '$.ShipIdent'), '') AS ship_ident
        FROM events
        WHERE event IN ('Loadout', 'LoadGame') AND json_extract_string(raw, '$.ShipID') IS NOT NULL
    """)
    con.execute("""
        CREATE OR REPLACE TEMP VIEW ship_display AS
        SELECT ship_id,
               arg_max(COALESCE(ship_name, ship_type || ' [' || COALESCE(ship_ident, ship_id) || ']'), timestamp) AS display_name
        FROM ship_changes GROUP BY ship_id
    """)

    print("Building vehicle-state boundary view (mirrors journal_deepdive.py section 5) ...")
    con.execute("""
        CREATE OR REPLACE TEMP VIEW vehicle_boundary AS
        SELECT timestamp, source_file,
          CASE
            WHEN event = 'LaunchSRV' THEN 'SRV'
            WHEN event IN ('DockSRV', 'SRVDestroyed') THEN 'SHIP'
            WHEN event = 'Disembark' THEN 'FOOT'
            WHEN event = 'Embark' AND json_extract_string(raw, '$.SRV') = 'true' THEN 'SRV'
            WHEN event = 'Embark' THEN 'SHIP'
          END AS state
        FROM events WHERE event IN ('LaunchSRV', 'DockSRV', 'SRVDestroyed', 'Disembark', 'Embark')
    """)

    has_star_system_col = "star_system" in con.execute("DESCRIBE events").fetchdf()["column_name"].values
    star_system_expr = "e.star_system" if has_star_system_col else "NULL"

    print("Running the one ASOF join pass over the full events table (this is the slow step) ...")
    df = con.execute(f"""
        SELECT e.timestamp, e.event, e.source_file, e.raw,
               {star_system_expr} AS star_system,
               json_extract_string(e.raw, '$.ScanType') AS scan_type,
               COALESCE(sd.display_name, 'Unknown ship (before first Loadout)') AS ship,
               COALESCE(vb.state, 'SHIP') AS vehicle_state
        FROM events e
        ASOF LEFT JOIN ship_changes sc ON e.timestamp >= sc.timestamp
        LEFT JOIN ship_display sd ON sc.ship_id = sd.ship_id
        ASOF LEFT JOIN vehicle_boundary vb ON e.timestamp >= vb.timestamp AND e.source_file = vb.source_file
    """).fetchdf()
    print(f"  {len(df):,} events fetched.")

    print("Classifying events into activity categories ...")
    df["category"] = [categorize(e, st) for e, st in zip(df["event"], df["scan_type"])]
    df = df.drop(columns=["scan_type"])

    print("Building session summary ...")
    sessions = con.execute("""
        SELECT source_file, MIN(timestamp) AS session_start, MAX(timestamp) AS session_end,
               COUNT(*) AS event_count
        FROM events GROUP BY source_file HAVING MIN(timestamp) IS NOT NULL
    """).fetchdf()
    sessions["duration_hours"] = (
        pd.to_datetime(sessions["session_end"]) - pd.to_datetime(sessions["session_start"])
    ).dt.total_seconds() / 3600.0

    print(f"Connecting to Postgres ...")
    pg = psycopg2.connect(pg_dsn)
    pg.autocommit = False
    cur = pg.cursor()

    print("Truncating existing events/sessions (safe to re-run this script) ...")
    cur.execute("TRUNCATE TABLE events, sessions")

    print("Loading sessions ...")
    buf = io.StringIO()
    sessions[["source_file", "session_start", "session_end", "event_count", "duration_hours"]].to_csv(
        buf, index=False, header=False)
    buf.seek(0)
    cur.copy_expert(
        "COPY sessions (source_file, session_start, session_end, event_count, duration_hours) "
        "FROM STDIN WITH (FORMAT csv)", buf)

    print("Loading events (chunked) ...")
    CHUNK = 200_000
    cols = ["timestamp", "event", "source_file", "raw", "star_system", "ship", "vehicle_state", "category"]
    total = len(df)
    for start in range(0, total, CHUNK):
        chunk = df.iloc[start:start + CHUNK]
        buf = io.StringIO()
        chunk[cols].to_csv(buf, index=False, header=False)
        buf.seek(0)
        cur.copy_expert(
            "COPY events (timestamp, event, source_file, raw, star_system, ship, vehicle_state, category) "
            "FROM STDIN WITH (FORMAT csv)", buf)
        print(f"  {min(start + CHUNK, total):,} / {total:,}")

    pg.commit()
    print("Done. Committed.")
    cur.close()
    pg.close()
    con.close()


if __name__ == "__main__":
    main()
