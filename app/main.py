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


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
